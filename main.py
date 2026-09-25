import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import JWTError, jwt

from database import (
    init_db,
    create_user,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
    save_history,
    get_user_history,
    get_history_item,
    delete_history_item,
)
from gemini_utils import (
    generate_home_recommendations,
    generate_party_recommendations,
    generate_jewelry_recommendations,
)

# ------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "pocketsmart-dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="PocketSmart AI - Your Smart Budget & Recommendation Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

if not os.path.isdir("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup():
    init_db()


# ------------------------------------------------------------------
# Auth helpers
# ------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


async def get_current_user_optional(request: Request):
    token = get_token_from_request(request)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            return None
    except JWTError:
        return None
    return get_user_by_id(user_id)


async def get_current_active_user(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": "/login"},
        )
    return user


def redirect_if_unauthenticated(request: Request):
    """Used by page routes: redirects to /login instead of raising a JSON 401."""
    user = None
    token = get_token_from_request(request)
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("user_id")
            if user_id:
                user = get_user_by_id(user_id)
        except JWTError:
            user = None
    return user


# ------------------------------------------------------------------
# Public pages
# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = redirect_if_unauthenticated(request)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    existing = get_user_by_username(username) or get_user_by_email(email)
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username or email already registered."},
            status_code=400,
        )
    hashed = hash_password(password)
    user_id = create_user(username, email, hashed)
    if not user_id:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Could not create account. Try a different username/email."},
            status_code=400,
        )
    token = create_access_token({"user_id": user_id, "sub": username})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=401,
        )
    token = create_access_token({"user_id": user["id"], "sub": user["username"]})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response


# OAuth2-style token endpoint (JSON), useful for /docs testing
@app.post("/token")
async def token_endpoint(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"user_id": user["id"], "sub": user["username"]})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/session-info")
async def session_info(request: Request):
    user = await get_current_user_optional(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user_id": user["id"], "username": user["username"]}


@app.get("/session-data")
async def session_data(current_user=Depends(get_current_active_user)):
    history = get_user_history(current_user["id"], limit=5)
    return {
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "email": current_user["email"],
        },
        "recent_history": history,
    }


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    history = get_user_history(user["id"], limit=10)
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "history": history}
    )


# ------------------------------------------------------------------
# Planner pages (GET - show forms)
# ------------------------------------------------------------------

@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner_page(request: Request):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("home_planner.html", {"request": request, "user": user})


@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner_page(request: Request):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("party_planner.html", {"request": request, "user": user})


@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner_page(request: Request):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("jewelry_planner.html", {"request": request, "user": user})


# ------------------------------------------------------------------
# Planner generation (POST - call Gemini via gemini_utils)
# ------------------------------------------------------------------

@app.post("/generate-home", response_class=HTMLResponse)
async def generate_home(
    request: Request,
    budget: float = Form(...),
    room_types: str = Form(...),  # comma-separated
    style_preference: str = Form("Modern Contemporary"),
    living_room_lights: int = Form(0),
    ceiling_fans: int = Form(0),
    dining_tables: int = Form(0),
):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    rooms = [r.strip() for r in room_types.split(",") if r.strip()]
    items = {
        "lights": living_room_lights,
        "ceiling_fans": ceiling_fans,
        "dining_tables": dining_tables,
    }

    result = generate_home_recommendations(budget, rooms, items, style_preference)

    history_id = save_history(
        user_id=user["id"],
        planner_type="home",
        query_summary=result["summary"],
        budget=budget,
        total_cost=result["total_cost"],
        input_details={"room_types": rooms, "items": items, "style": style_preference},
        results_json=result["recommendations"],
    )
    result["history_id"] = history_id

    return templates.TemplateResponse(
        "results.html", {"request": request, "user": user, "result": result, "planner_title": "Home Interior"}
    )


@app.post("/generate-party", response_class=HTMLResponse)
async def generate_party(
    request: Request,
    budget: float = Form(...),
    guest_count: int = Form(...),
    event_type: str = Form(...),
    venue_details: str = Form(...),
    special_notes: str = Form(""),
):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    result = generate_party_recommendations(budget, guest_count, event_type, venue_details, special_notes)

    history_id = save_history(
        user_id=user["id"],
        planner_type="party",
        query_summary=result["summary"],
        budget=budget,
        total_cost=result["total_cost"],
        input_details={
            "guest_count": guest_count,
            "event_type": event_type,
            "venue_details": venue_details,
            "special_notes": special_notes,
        },
        results_json=result["recommendations"],
    )
    result["history_id"] = history_id

    return templates.TemplateResponse(
        "results.html", {"request": request, "user": user, "result": result, "planner_title": "Party"}
    )


@app.post("/generate-jewelry", response_class=HTMLResponse)
async def generate_jewelry(
    request: Request,
    budget: float = Form(...),
    occasion: str = Form(...),
    style_preference: str = Form(...),
    metal_preference: str = Form("Any"),
    outfit_image: Optional[UploadFile] = File(None),
):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    image_bytes = None
    mime_type = None
    if outfit_image and outfit_image.filename:
        image_bytes = await outfit_image.read()
        mime_type = outfit_image.content_type

    result = generate_jewelry_recommendations(
        budget, occasion, style_preference, metal_preference, image_bytes, mime_type
    )

    history_id = save_history(
        user_id=user["id"],
        planner_type="jewelry",
        query_summary=result["summary"],
        budget=budget,
        total_cost=result["total_cost"],
        input_details={
            "occasion": occasion,
            "style_preference": style_preference,
            "metal_preference": metal_preference,
            "had_image": bool(image_bytes),
        },
        results_json=result["recommendations"],
    )
    result["history_id"] = history_id

    return templates.TemplateResponse(
        "results.html", {"request": request, "user": user, "result": result, "planner_title": "Jewelry"}
    )


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    items = get_user_history(user["id"], limit=50)
    return templates.TemplateResponse("history.html", {"request": request, "user": user, "history": items})


@app.get("/recommendations-details/{history_id}", response_class=HTMLResponse)
async def recommendation_details(request: Request, history_id: int):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    item = get_history_item(history_id, user["id"])
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    result = {
        "planner_type": item["planner_type"],
        "budget": item["budget"],
        "total_cost": item["total_cost"],
        "budget_status": "Within Budget" if item["total_cost"] <= item["budget"] else "Exceeded Budget",
        "summary": item["query_summary"],
        "recommendations": item["results_json"],
        "history_id": item["id"],
    }
    return templates.TemplateResponse(
        "results.html",
        {"request": request, "user": user, "result": result, "planner_title": item["planner_type"].title()},
    )


@app.post("/history/{history_id}/delete")
async def delete_history(request: Request, history_id: int):
    user = redirect_if_unauthenticated(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    delete_history_item(history_id, user["id"])
    return RedirectResponse(url="/history", status_code=status.HTTP_303_SEE_OTHER)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
