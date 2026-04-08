"""Skills（技能）管理路由 — 提供 Skill 的 CRUD、安装、编辑、回滚和启停控制。

功能概览：
- GET  /api/skills          — 列出所有可用技能（public + custom）
- POST /api/skills/install   — 从 .skill 压缩包安装新技能
- GET  /api/skills/custom    — 仅列出用户自定义技能
- GET  /api/skills/custom/{name}     — 获取自定义技能内容（含 SKILL.md 源码）
- PUT  /api/skills/custom/{name}     — 编辑自定义技能（含安全扫描 + 历史留痕）
- DEL  /api/skills/custom/{name}     — 删除自定义技能（含历史归档）
- GET  /api/skills/custom/{name}/history  — 查看技能变更历史
- POST /api/skills/custom/{name}/rollback — 回滚到历史版本
- GET  /api/skills/{name}     — 获取单个技能详情
- PUT  /api/skills/{name}     — 更新技能的启用/禁用状态

安全机制：
- 编辑/回滚操作均经过安全扫描（scan_skill_content）
- 所有写操作使用 atomic_write 保证原子性
- 变更自动记录到 history 文件，支持审计和回滚
- 安装操作限定在 thread 虚拟路径内，防止目录穿越

配置存储：
- 技能的 enabled 状态持久化到 extensions_config.json
- 自定义技能的 SKILL.md 存储在 custom_skills_dir 目录下
"""

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.agents.lead_agent.prompt import refresh_skills_system_prompt_cache_async
from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from deerflow.skills import Skill, load_skills
from deerflow.skills.installer import SkillAlreadyExistsError, install_skill_from_archive
from deerflow.skills.manager import (
    append_history,
    atomic_write,
    custom_skill_exists,
    ensure_custom_skill_is_editable,
    get_custom_skill_dir,
    get_custom_skill_file,
    get_skill_history_file,
    read_custom_skill_content,
    read_history,
    validate_skill_markdown_content,
)
from deerflow.skills.security_scanner import scan_skill_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"])


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


class CustomSkillContentResponse(SkillResponse):
    content: str = Field(..., description="Raw SKILL.md content")


class CustomSkillUpdateRequest(BaseModel):
    content: str = Field(..., description="Replacement SKILL.md content")


class CustomSkillHistoryResponse(BaseModel):
    history: list[dict]


class SkillRollbackRequest(BaseModel):
    history_index: int = Field(default=-1, description="History entry index to restore from, defaulting to the latest change.")


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
    )


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills() -> SkillsListResponse:
    try:
        skills = load_skills(enabled_only=False)
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(request: SkillInstallRequest) -> SkillInstallResponse:
    try:
        # 安全边界：先把虚拟路径解析到线程沙盒目录，避免跨目录安装任意文件。
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)
        result = install_skill_from_archive(skill_file_path)
        await refresh_skills_system_prompt_cache_async()
        return SkillInstallResponse(**result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}")


@router.get("/skills/custom", response_model=SkillsListResponse, summary="List Custom Skills")
async def list_custom_skills() -> SkillsListResponse:
    try:
        skills = [skill for skill in load_skills(enabled_only=False) if skill.category == "custom"]
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error("Failed to list custom skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list custom skills: {str(e)}")


@router.get("/skills/custom/{skill_name}", response_model=CustomSkillContentResponse, summary="Get Custom Skill Content")
async def get_custom_skill(skill_name: str) -> CustomSkillContentResponse:
    try:
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name and s.category == "custom"), None)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        return CustomSkillContentResponse(**_skill_to_response(skill).model_dump(), content=read_custom_skill_content(skill_name))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get custom skill: {str(e)}")


@router.put("/skills/custom/{skill_name}", response_model=CustomSkillContentResponse, summary="Edit Custom Skill")
async def update_custom_skill(skill_name: str, request: CustomSkillUpdateRequest) -> CustomSkillContentResponse:
    try:
        # 更新链路：可编辑性校验 -> 语法校验 -> 安全扫描 -> 原子写入 -> 历史留痕。
        # 该顺序保证“要么完整成功，要么可审计回滚”。
        ensure_custom_skill_is_editable(skill_name)
        validate_skill_markdown_content(skill_name, request.content)
        scan = await scan_skill_content(request.content, executable=False, location=f"{skill_name}/SKILL.md")
        if scan.decision == "block":
            raise HTTPException(status_code=400, detail=f"Security scan blocked the edit: {scan.reason}")
        skill_file = get_custom_skill_dir(skill_name) / "SKILL.md"
        prev_content = skill_file.read_text(encoding="utf-8")
        atomic_write(skill_file, request.content)
        append_history(
            skill_name,
            {
                "action": "human_edit",
                "author": "human",
                "thread_id": None,
                "file_path": "SKILL.md",
                "prev_content": prev_content,
                "new_content": request.content,
                "scanner": {"decision": scan.decision, "reason": scan.reason},
            },
        )
        await refresh_skills_system_prompt_cache_async()
        return await get_custom_skill(skill_name)
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to update custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update custom skill: {str(e)}")


@router.delete("/skills/custom/{skill_name}", summary="Delete Custom Skill")
async def delete_custom_skill(skill_name: str) -> dict[str, bool]:
    try:
        ensure_custom_skill_is_editable(skill_name)
        skill_dir = get_custom_skill_dir(skill_name)
        prev_content = read_custom_skill_content(skill_name)
        append_history(
            skill_name,
            {
                "action": "human_delete",
                "author": "human",
                "thread_id": None,
                "file_path": "SKILL.md",
                "prev_content": prev_content,
                "new_content": None,
                "scanner": {"decision": "allow", "reason": "Deletion requested."},
            },
        )
        shutil.rmtree(skill_dir)
        await refresh_skills_system_prompt_cache_async()
        return {"success": True}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete custom skill: {str(e)}")


@router.get("/skills/custom/{skill_name}/history", response_model=CustomSkillHistoryResponse, summary="Get Custom Skill History")
async def get_custom_skill_history(skill_name: str) -> CustomSkillHistoryResponse:
    try:
        if not custom_skill_exists(skill_name) and not get_skill_history_file(skill_name).exists():
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        return CustomSkillHistoryResponse(history=read_history(skill_name))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to read history for %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read history: {str(e)}")


@router.post("/skills/custom/{skill_name}/rollback", response_model=CustomSkillContentResponse, summary="Rollback Custom Skill")
async def rollback_custom_skill(skill_name: str, request: SkillRollbackRequest) -> CustomSkillContentResponse:
    try:
        if not custom_skill_exists(skill_name) and not get_skill_history_file(skill_name).exists():
            raise HTTPException(status_code=404, detail=f"Custom skill '{skill_name}' not found")
        history = read_history(skill_name)
        if not history:
            raise HTTPException(status_code=400, detail=f"Custom skill '{skill_name}' has no history")
        record = history[request.history_index]
        target_content = record.get("prev_content")
        if target_content is None:
            raise HTTPException(status_code=400, detail="Selected history entry has no previous content to roll back to")
        validate_skill_markdown_content(skill_name, target_content)
        scan = await scan_skill_content(target_content, executable=False, location=f"{skill_name}/SKILL.md")
        skill_file = get_custom_skill_file(skill_name)
        current_content = skill_file.read_text(encoding="utf-8") if skill_file.exists() else None
        history_entry = {
            "action": "rollback",
            "author": "human",
            "thread_id": None,
            "file_path": "SKILL.md",
            "prev_content": current_content,
            "new_content": target_content,
            "rollback_from_ts": record.get("ts"),
            "scanner": {"decision": scan.decision, "reason": scan.reason},
        }
        if scan.decision == "block":
            append_history(skill_name, history_entry)
            raise HTTPException(status_code=400, detail=f"Rollback blocked by security scanner: {scan.reason}")
        atomic_write(skill_file, target_content)
        append_history(skill_name, history_entry)
        await refresh_skills_system_prompt_cache_async()
        return await get_custom_skill(skill_name)
    except HTTPException:
        raise
    except IndexError:
        raise HTTPException(status_code=400, detail="history_index is out of range")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to roll back custom skill %s: %s", skill_name, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to roll back custom skill: {str(e)}")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(skill_name: str) -> SkillResponse:
    try:
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return _skill_to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update a skill's enabled status by modifying the extensions_config.json file.",
)
async def update_skill(skill_name: str, request: SkillUpdateRequest) -> SkillResponse:
    try:
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info(f"No existing extensions config found. Creating new config at: {config_path}")

        extensions_config = get_extensions_config()
        extensions_config.skills[skill_name] = SkillStateConfig(enabled=request.enabled)

        config_data = {
            "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
            "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Skills configuration updated and saved to: {config_path}")
        reload_extensions_config()
        await refresh_skills_system_prompt_cache_async()

        skills = load_skills(enabled_only=False)
        updated_skill = next((s for s in skills if s.name == skill_name), None)

        if updated_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload skill '{skill_name}' after update")

        logger.info(f"Skill '{skill_name}' enabled status updated to {request.enabled}")
        return _skill_to_response(updated_skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")
