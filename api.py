# api.py — HTML 前端业务接口（FastAPI）
# 启动：uvicorn api:app --port 8000
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from typing import List

load_dotenv()

from core.database import init_db
init_db()

from audit.audit_service import log_event
from auth.auth_service import (
    authenticate_user, update_display_name, update_password, update_avatar,
    create_user, list_users, update_user_role, toggle_user_active, delete_user,
)
from audit.audit_service import get_logs, get_summary_stats
from data.document_service import generate_title_from_requirements, save_document
from data.conversation_service import (
    create_conversation,
    delete_conversation,
    generate_title_from_message,
    get_conversation,
    get_conversations,
    get_messages,
    save_message,
    update_conversation_title,
)

# ── JWT 配置 ──────────────────────────────────────────
_SECRET_KEY         = "hngd-knowledge-agent-secret"   # 生产环境改为环境变量
_ALGORITHM          = "HS256"
_TOKEN_EXPIRE_HOURS = 8
_EMBED_TOKEN        = os.getenv("EMBED_TOKEN", "hngd-embed-2024")


def _create_token(user: dict) -> str:
    payload = {
        "sub":          str(user["user_id"]),
        "username":     user["username"],
        "role":         user["role"],
        "display_name": user["display_name"],
        "exp":          datetime.utcnow() + timedelta(hours=_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


# ── FastAPI 应用 ───────────────────────────────────────
app = FastAPI(title="HNGD 知识助手 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 本地 HTML 文件开发用；生产环境改为具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── JWT 鉴权依赖 ───────────────────────────────────────
_bearer = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """校验 Bearer Token，返回当前用户信息字典。"""
    try:
        payload = jwt.decode(credentials.credentials, _SECRET_KEY, algorithms=[_ALGORITHM])
        return {
            "user_id":      int(payload["sub"]),
            "username":     payload["username"],
            "role":         payload["role"],
            "display_name": payload["display_name"],
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")


# ── SSE 工具函数 ───────────────────────────────────────
def _sse(data: dict) -> str:
    """将字典序列化为 SSE data 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 请求/响应模型 ──────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str
    role: str           # 前端选择的身份："user" 或 "admin"


class LoginResponse(BaseModel):
    token:        str
    user_id:      int
    username:     str
    role:         str
    display_name: str
    avatar:       str | None = None


class ChatRequest(BaseModel):
    message:         str
    conversation_id: int | None = None
    mode:            str = "rag"   # "rag" | "data" | "write" | "api"


class DocContentRequest(BaseModel):
    requirements:      str
    outline:           str
    reference_context: str = ""


class UpdateDisplayNameRequest(BaseModel):
    display_name: str


class UpdateAvatarRequest(BaseModel):
    avatar: str


class UpdatePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username:     str
    password:     str
    display_name: str = ""
    role:         str = "user"   # visitor | user | admin


class UpdateRoleRequest(BaseModel):
    role: str                    # visitor | user | admin


class UpdateActiveRequest(BaseModel):
    is_active: bool


class EmbedChatRequest(BaseModel):
    message:     str
    thread_id:   str | None = None
    embed_token: str


# ── 文档编写辅助 ───────────────────────────────────────
def _auto_save_document(user: dict, requirements: str, outline: str,
                        content: str, reference_context: str) -> int | None:
    """生成完成后自动保存文档记录并同步创建侧边栏对话条目。"""
    try:
        doc_title = generate_title_from_requirements(outline or requirements)
        doc_id = save_document(
            user_id           = user["user_id"],
            title             = doc_title,
            requirements      = requirements,
            outline           = outline,
            content           = content,
            reference_context = reference_context,
        )
        conv_id = create_conversation(user["user_id"], title=doc_title)
        save_message(conv_id, "user",      f"📝 文档撰写需求：\n{requirements}")
        save_message(conv_id, "assistant", content)
        return doc_id
    except Exception:
        return None


# ── 登录接口（原有，不改动）────────────────────────────
@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)

    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 角色校验：管理员只能以管理员身份登录，用户只能以用户身份登录
    if user["role"] != req.role:
        role_label = "管理员" if req.role == "admin" else "普通用户"
        raise HTTPException(status_code=401, detail=f"该账号不是{role_label}账号，请切换登录身份")

    log_event(user["user_id"], user["username"], "login")

    return LoginResponse(
        token        = _create_token(user),
        user_id      = user["user_id"],
        username     = user["username"],
        role         = user["role"],
        display_name = user["display_name"],
        avatar       = user.get("avatar"),
    )


# ── 登出接口 ───────────────────────────────────────────
@app.post("/api/auth/logout")
def logout(user: dict = Depends(verify_token)):
    """记录登出审计日志；Token 失效由前端清除 localStorage 实现。"""
    log_event(user["user_id"], user["username"], "logout")
    return {"ok": True}


# ── 对话列表接口 ───────────────────────────────────────
@app.get("/api/conversations")
def list_convs(user: dict = Depends(verify_token)):
    """获取当前用户的对话列表（按 updated_at 降序）。"""
    return get_conversations(user["user_id"])


@app.post("/api/conversations")
def create_conv(user: dict = Depends(verify_token)):
    """新建对话，返回 {id, title}。"""
    conv_id = create_conversation(user["user_id"])
    return {"id": conv_id, "title": "新对话"}


@app.delete("/api/conversations/{conv_id}")
def delete_conv(conv_id: int, user: dict = Depends(verify_token)):
    """删除对话及其所有消息（级联）。"""
    ok = delete_conversation(conv_id, user["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在或无权限")
    return {"ok": True}


@app.get("/api/conversations/{conv_id}/messages")
def get_conv_messages(conv_id: int, user: dict = Depends(verify_token)):
    """获取对话的全部消息，同时返回对话基本信息。"""
    conv = get_conversation(conv_id, user["user_id"])
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在或无权限")
    msgs = get_messages(conv_id, user["user_id"])
    return {"conversation": conv, "messages": msgs}


# ── 流式对话接口 ───────────────────────────────────────
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(verify_token)):
    """
    发送消息，以 SSE 流式返回思考步骤和最终回答。

    SSE 事件类型：
      init   — 含 conversation_id 和 title（首条消息时对话自动命名）
      step   — LangGraph 工具调用/返回步骤（对应 steps_log）
      answer — 最终回答，含 warning 和 agent 字段
      done   — 流结束信号
      error  — 执行异常
    """
    async def event_gen():
        # 延迟导入避免模块加载时阻塞（agent.py 会初始化 LLM）
        from agent import chat, chat_direct

        # 1. 处理 conversation_id
        conv_id = req.conversation_id
        if conv_id is None:
            conv_id = create_conversation(user["user_id"])

        # 2. 保存用户消息
        save_message(conv_id, "user", req.message)

        # 3. 首条消息时自动生成对话标题
        conv  = get_conversation(conv_id, user["user_id"])
        title = conv["title"] if conv else "新对话"
        if title == "新对话":
            title = generate_title_from_message(req.message)
            update_conversation_title(conv_id, user["user_id"], title)

        # 4. 推送 init 事件（前端更新 conversation_id 和标题）
        yield _sse({"type": "init", "conversation_id": conv_id, "title": title})

        # 5. 根据 mode 选择调用方式（与 chat_page.py 逻辑一致）
        thread_id    = f"conversation-{conv_id}"
        user_context = {
            "user_id":  user["user_id"],
            "username": user["username"],
            "role":     user["role"],
        }

        mode_calls = {
            "rag":   lambda: chat(req.message, thread_id, user_context=user_context),
            "data":  lambda: chat_direct("data_agent", req.message, thread_id, user_context=user_context),
            "write": lambda: chat_direct("rag_agent",  req.message, thread_id, user_context=user_context),
            "api":   lambda: chat_direct("api_agent",  req.message, thread_id, user_context=user_context),
        }
        call_fn = mode_calls.get(req.mode, mode_calls["rag"])

        # 6. 在线程池中运行同步 LangGraph（避免阻塞事件循环）
        try:
            response, steps, agent_used = await asyncio.to_thread(call_fn)
        except Exception as e:
            yield _sse({"type": "error", "text": f"执行失败：{e}"})
            yield _sse({"type": "done"})
            return

        # 7. 推送思考步骤
        for step in (steps or []):
            yield _sse({"type": "step", "text": step})

        # 8. 推送最终回答
        is_warning = any(kw in response for kw in ("未能找到", "未找到", "没有找到"))
        yield _sse({
            "type":    "answer",
            "text":    response,
            "warning": is_warning,
            "agent":   agent_used or "",
        })

        # 9. 保存助手消息 + 写审计日志
        save_message(conv_id, "assistant", response, steps_log=steps, agent_used=agent_used)
        log_event(
            user_id    = user["user_id"],
            username   = user["username"],
            action     = "chat",
            agent_used = agent_used,
            question   = req.message,
        )

        yield _sse({"type": "done"})

    return StreamingResponse(
        event_gen(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",    # 禁止 Nginx 缓冲，确保实时推送
        },
    )


# ── 用户设置接口 ───────────────────────────────────────
@app.put("/api/user/display-name")
def api_update_display_name(req: UpdateDisplayNameRequest, user: dict = Depends(verify_token)):
    """修改当前用户的显示名称。"""
    if len(req.display_name) > 50:
        raise HTTPException(status_code=400, detail="显示名称长度不能超过 50 个字符")
    ok, msg = update_display_name(user["user_id"], req.display_name)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    log_event(user["user_id"], user["username"], "update_display_name")
    return {"ok": True, "display_name": req.display_name.strip()}


@app.put("/api/user/avatar")
def api_update_avatar(req: UpdateAvatarRequest, user: dict = Depends(verify_token)):
    """更新当前用户的头像（base64 图片或 SVG data URL）。"""
    if not req.avatar or not req.avatar.startswith("data:"):
        raise HTTPException(status_code=400, detail="头像格式无效")
    ok, msg = update_avatar(user["user_id"], req.avatar)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    log_event(user["user_id"], user["username"], "update_avatar")
    return {"ok": True}


@app.put("/api/user/password")
def api_update_password(req: UpdatePasswordRequest, user: dict = Depends(verify_token)):
    """修改当前用户的登录密码，需提供旧密码验证。"""
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度至少 6 位")
    ok, msg = update_password(user["user_id"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    log_event(user["user_id"], user["username"], "update_password")
    return {"ok": True}


# ── 文档编写接口 ───────────────────────────────────────
@app.post("/api/doc/generate-outline")
async def doc_generate_outline(
    requirements: str                  = Form(...),
    files:        List[UploadFile]     = File(default=[]),
    user:         dict                 = Depends(verify_token),
):
    """
    Step 1：根据用户需求（+ 可选附件）调用 doc_agent 生成文档目录。

    返回 {outline, steps_log, reference_context}。
    reference_context 由服务端解析附件后生成，前端原样存储并在 Step 2 透传。
    """
    from pathlib import Path
    from data.file_parser import _extract_by_extension
    from agent import chat_direct

    # 解析上传附件
    file_contents = []
    for f in files:
        raw   = await f.read()
        name  = f.filename or "unknown"
        ext   = Path(name).suffix.lower()
        text  = _extract_by_extension(name, ext, raw)
        if len(text) > 8000:
            text = text[:8000] + f"\n\n...（内容过长，已截断，共 {len(text)} 字符）"
        file_contents.append((name, text))

    # 拼附件上下文
    attachment_context = ""
    if file_contents:
        parts = [f"[附件{i}：{name}]\n{text}" for i, (name, text) in enumerate(file_contents, 1)]
        attachment_context = "=== 用户上传附件 ===\n" + "\n\n".join(parts) + "\n\n"

    # 与 doc_page.py 保持一致的 prompt 格式
    if attachment_context:
        outline_prompt = f"【任务】生成文档目录\n\n{attachment_context}【用户需求】\n{requirements}"
    else:
        outline_prompt = f"【任务】生成文档目录\n\n【用户需求】\n{requirements}"

    thread_id    = f"doc_outline_{user['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    user_context = {"user_id": user["user_id"], "username": user["username"], "role": user["role"]}

    try:
        outline, steps_log, _ = await asyncio.to_thread(
            lambda: chat_direct(
                "doc_agent", outline_prompt, thread_id,
                user_context=user_context, username=user["username"],
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"目录生成失败：{e}")

    log_event(user["user_id"], user["username"], "doc_outline_generate", status="success")

    return {
        "outline":           outline,
        "steps_log":         steps_log or [],
        "reference_context": attachment_context,
    }


@app.post("/api/doc/generate-content")
async def doc_generate_content(req: DocContentRequest, user: dict = Depends(verify_token)):
    """
    Step 2：根据已确认目录调用 doc_agent 生成完整文档，并自动保存到历史记录。

    返回 {content, steps_log, document_id}。
    """
    from agent import chat_direct

    # 与 doc_page.py 保持一致的 prompt 格式
    content_prompt = (
        f"【任务】生成文档内容\n\n"
        f"{req.reference_context}"
        f"【原始需求】\n{req.requirements}\n\n"
        f"【已确认的目录结构（严格遵循此结构）】\n{req.outline}"
    )

    thread_id    = f"doc_gen_{user['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    user_context = {"user_id": user["user_id"], "username": user["username"], "role": user["role"]}

    try:
        content, steps_log, _ = await asyncio.to_thread(
            lambda: chat_direct(
                "doc_agent", content_prompt, thread_id,
                user_context=user_context, username=user["username"],
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档生成失败：{e}")

    doc_id = await asyncio.to_thread(
        lambda: _auto_save_document(
            user, req.requirements, req.outline, content, req.reference_context
        )
    )

    log_event(user["user_id"], user["username"], "doc_generate", status="success")

    return {
        "content":     content,
        "steps_log":   steps_log or [],
        "document_id": doc_id,
    }


# ── 管理员权限依赖 ──────────────────────────────────────
def require_admin(user: dict = Depends(verify_token)) -> dict:
    """校验当前用户是否为管理员，否则返回 403。"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ── 管理员接口 — 用户管理 ───────────────────────────────
@app.get("/api/admin/stats")
def admin_get_stats(user: dict = Depends(require_admin)):
    """返回系统统计摘要：用户总数、今日活跃用户、今日对话数、历史总对话量。"""
    return get_summary_stats()


@app.get("/api/admin/users")
def admin_list_users(user: dict = Depends(require_admin)):
    """返回全部用户列表。"""
    return list_users()


@app.post("/api/admin/users")
def admin_create_user(req: CreateUserRequest, user: dict = Depends(require_admin)):
    """创建新用户，用户名重复时返回 409。"""
    _VALID_ROLES = {"visitor", "user", "admin"}
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"无效角色，可选值：{', '.join(_VALID_ROLES)}")
    ok = create_user(req.username, req.password, req.display_name, req.role)
    if not ok:
        raise HTTPException(status_code=409, detail=f"用户名「{req.username}」已存在")
    log_event(user["user_id"], user["username"], "admin_op", status="success")
    return {"ok": True}


@app.put("/api/admin/users/{target_id}/role")
def admin_update_role(target_id: int, req: UpdateRoleRequest, user: dict = Depends(require_admin)):
    """修改指定用户的角色。"""
    _VALID_ROLES = {"visitor", "user", "admin"}
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"无效角色，可选值：{', '.join(_VALID_ROLES)}")
    ok = update_user_role(target_id, req.role)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    log_event(user["user_id"], user["username"], "admin_op", status="success")
    return {"ok": True}


@app.put("/api/admin/users/{target_id}/active")
def admin_toggle_active(target_id: int, req: UpdateActiveRequest, user: dict = Depends(require_admin)):
    """启用或禁用指定用户；不允许对当前登录账户执行禁用操作。"""
    if target_id == user["user_id"] and not req.is_active:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账户")
    ok = toggle_user_active(target_id, req.is_active)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    log_event(user["user_id"], user["username"], "admin_op", status="success")
    return {"ok": True}


@app.delete("/api/admin/users/{target_id}")
def admin_delete_user(target_id: int, user: dict = Depends(require_admin)):
    """删除用户及其全部历史数据（对话、消息、审计日志、文档历史），不可撤销。"""
    if target_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账户")
    ok = delete_user(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    log_event(user["user_id"], user["username"], "admin_op", status="success")
    return {"ok": True}


# ── 管理员接口 — 审计日志 ───────────────────────────────
@app.get("/api/admin/logs")
def admin_get_logs(
    username:  str | None = None,
    action:    str | None = None,
    date_from: str | None = None,
    date_to:   str | None = None,
    limit:     int        = 200,
    offset:    int        = 0,
    user:      dict       = Depends(require_admin),
):
    """查询审计日志，支持按用户名、操作类型、日期范围过滤。"""
    limit = min(limit, 500)   # 最大 500 条
    logs  = get_logs(
        limit=limit, offset=offset,
        username=username, action=action,
        date_from=date_from, date_to=date_to,
    )
    return {"total": len(logs), "logs": logs}


# ── 管理员接口 — 知识库（Dify 代理）──────────────────────
@app.get("/api/admin/kb/datasets")
async def admin_list_datasets(
    page:  int  = 1,
    limit: int  = 20,
    user:  dict = Depends(require_admin),
):
    """获取 Dify 知识库列表（分页）。未配置 DIFY_DATASET_KEY 时返回 503。"""
    import os
    if not os.environ.get("DIFY_DATASET_KEY"):
        raise HTTPException(status_code=503, detail="未配置 DIFY_DATASET_KEY，请在 .env 文件中配置后重启服务")
    from data.dify_service import list_datasets
    try:
        return await asyncio.to_thread(list_datasets, page, limit)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/admin/kb/datasets/{dataset_id}/documents")
async def admin_list_documents(
    dataset_id: str,
    page:       int  = 1,
    limit:      int  = 20,
    user:       dict = Depends(require_admin),
):
    """获取指定知识库的文档列表（分页）。"""
    import os
    if not os.environ.get("DIFY_DATASET_KEY"):
        raise HTTPException(status_code=503, detail="未配置 DIFY_DATASET_KEY，请在 .env 文件中配置后重启服务")
    from data.dify_service import list_documents
    try:
        return await asyncio.to_thread(list_documents, dataset_id, page, limit)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── 管理员接口 — 本地数据文件 ─────────────────────────────
@app.get("/api/admin/data-files")
def admin_list_data_files(user: dict = Depends(require_admin)):
    """列出 DATA_DIR 目录下的数据文件，供管理员界面展示。"""
    import os
    from pathlib import Path

    data_dir = os.environ.get("DATA_DIR", "").strip()
    if not data_dir:
        raise HTTPException(status_code=503, detail="未配置 DATA_DIR，请在 .env 文件中配置后重启服务")

    dir_path = Path(data_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=503, detail=f"DATA_DIR 目录不存在：{data_dir}")

    files = []
    for f in sorted(dir_path.iterdir()):
        if f.is_file():
            ext = f.suffix.lower().lstrip(".")
            size_kb = round(f.stat().st_size / 1024, 1)
            files.append({"name": f.name, "ext": ext or "—", "size_kb": size_kb})

    return {"dir": str(data_dir), "files": files}


# ── 接口配置存取 ──────────────────────────────────────────
_IFACE_CONFIGS_PATH = Path(__file__).parent / "project_documents" / "interface_configs.json"


@app.get("/api/interface-configs")
def get_interface_configs(user: dict = Depends(verify_token)):
    """读取接口配置文件，不存在时返回空结构。"""
    if not _IFACE_CONFIGS_PATH.exists():
        return {"groups": [], "interfaces": []}
    try:
        return json.loads(_IFACE_CONFIGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"groups": [], "interfaces": []}


@app.post("/api/interface-configs")
async def save_interface_configs(request: Request, user: dict = Depends(verify_token)):
    """覆盖写入接口配置文件。"""
    body = await request.json()
    _IFACE_CONFIGS_PATH.write_text(
        json.dumps(body, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True}


# ── 嵌入式对话接口（无需 JWT，embed_token 鉴权）──────────────
_EMBED_HTML = Path(__file__).parent / "html_files" / "chat-embed.html"


@app.get("/embed/chat")
def embed_chat_page():
    """提供网页嵌入版对话页面，供 iframe 加载。"""
    if not _EMBED_HTML.exists():
        raise HTTPException(status_code=404, detail="嵌入页面尚未部署")
    return FileResponse(_EMBED_HTML, media_type="text/html")


@app.get("/static/chat-ball.js")
def serve_chat_ball_js():
    """提供聊天球 widget 脚本，外部前端通过 <script src> 引入。"""
    js_path = Path(__file__).parent / "html_files" / "chat-ball.js"
    if not js_path.exists():
        raise HTTPException(status_code=404, detail="chat-ball.js 尚未部署")
    return FileResponse(js_path, media_type="application/javascript")


@app.post("/api/embed/chat")
async def embed_chat(req: EmbedChatRequest):
    """
    嵌入式对话接口，支持两种调用模式：
    - 单轮（聊天球）：不传 thread_id，每次生成新 UUID，对话无上下文
    - 多轮（网页嵌入）：传入 thread_id，LangGraph 保留会话内上下文
    """
    if req.embed_token != _EMBED_TOKEN:
        raise HTTPException(status_code=401, detail="embed_token 无效")

    thread_id    = req.thread_id or f"embed-{uuid.uuid4().hex}"
    user_context = {"user_id": 0, "username": "embed_guest", "role": "visitor"}

    from agent import chat as agent_chat
    try:
        response, _steps, _agent = await asyncio.to_thread(
            lambda: agent_chat(req.message, thread_id, user_context=user_context)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话失败：{e}")

    return {"response": response, "thread_id": thread_id}
