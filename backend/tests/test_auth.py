from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.main import app
from app.models import User
from tests.conftest import PASSWORD, sign_up
from tests.test_sessions import run_interview


def token_for(user_id, *, secret=None, expires_in=timedelta(minutes=5), include_exp=True) -> dict:
    payload = {"sub": str(user_id)}
    if include_exp:
        payload["exp"] = datetime.now(timezone.utc) + expires_in
    return {"Authorization": f"Bearer {jwt.encode(payload, secret or settings.jwt_secret, algorithm='HS256')}"}


async def test_duplicate_email_is_rejected_case_insensitively(anonymous_client):
    email = await sign_up(anonymous_client)
    duplicate = await anonymous_client.post("/api/auth/register", json={"email": email.upper(), "password": PASSWORD})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["error"] == "email_taken"


async def test_register_response_shape(anonymous_client):
    email = f"pytest-{uuid4().hex[:12]}@example.com"
    response = await anonymous_client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    body = response.json()
    assert response.status_code == 201
    assert body["email"] == email
    assert set(body) == {"id", "email", "created_at"}


async def test_password_is_stored_hashed(anonymous_client):
    email = await sign_up(anonymous_client)
    async with app.state.db_sessionmaker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert user.hashed_password != PASSWORD
    assert user.hashed_password.startswith("$2b$")


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "pytest-short@example.com", "password": "short"},
        {"email": "pytest-long@example.com", "password": "x" * 73},
        {"email": "pytest-bytes@example.com", "password": "é" * 40},  # 40 characters but 80 bytes
    ],
)
async def test_register_rejects_bad_input(anonymous_client, payload):
    response = await anonymous_client.post("/api/auth/register", json=payload)
    assert response.status_code == 422


async def test_login_returns_working_token(anonymous_client):
    email = await sign_up(anonymous_client)
    response = await anonymous_client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    body = response.json()
    assert response.status_code == 200 and body["token_type"] == "bearer"

    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    lifetime = datetime.fromtimestamp(claims["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(minutes=settings.jwt_expire_minutes - 1) < lifetime <= timedelta(minutes=settings.jwt_expire_minutes)

    history = await anonymous_client.get("/api/interview/history", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert history.status_code == 200


async def test_wrong_password_and_unknown_email_look_identical(anonymous_client):
    email = await sign_up(anonymous_client)
    wrong_password = await anonymous_client.post("/api/auth/login", json={"email": email, "password": "not-the-password"})
    unknown_email = await anonymous_client.post(
        "/api/auth/login", json={"email": "pytest-nobody@example.com", "password": PASSWORD}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


PROTECTED = [
    ("post", "/api/interview/start", {"data": {"subject": "Python"}}),
    ("post", "/api/interview/submit-answer", {"json": {"session_id": str(uuid4()), "answer": "x"}}),
    ("post", "/api/interview/get-feedback", {"json": {"session_id": str(uuid4())}}),
    ("get", "/api/interview/history", {}),
    ("get", f"/api/interview/{uuid4()}", {}),
]


@pytest.mark.parametrize("method,path,kwargs", PROTECTED)
async def test_interview_routes_require_a_token(anonymous_client, method, path, kwargs):
    response = await getattr(anonymous_client, method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_bad_tokens_are_rejected(client, anonymous_client):
    good_token = client.headers["Authorization"].split()[1]
    user_id = jwt.decode(good_token, settings.jwt_secret, algorithms=["HS256"])["sub"]
    assert (await client.get("/api/interview/history")).status_code == 200

    bad = {
        "garbage": {"Authorization": "Bearer not.a.jwt"},
        "expired": token_for(user_id, expires_in=timedelta(minutes=-1)),
        "wrong secret": token_for(user_id, secret="x" * 40),
        "no expiry": token_for(user_id, include_exp=False),
        "unknown user": token_for(uuid4()),
    }
    for name, headers in bad.items():
        response = await anonymous_client.get("/api/interview/history", headers=headers)
        assert response.status_code == 401, name


async def test_users_cannot_see_each_others_interviews(client, other_client, created_sessions):
    session_id, _ = await run_interview(client, created_sessions, "Python", [f"ans-{i}" for i in range(5)])

    assert (await client.get(f"/api/interview/{session_id}")).status_code == 200
    assert session_id in [i["id"] for i in (await client.get("/api/interview/history")).json()]

    detail = await other_client.get(f"/api/interview/{session_id}")
    submit = await other_client.post("/api/interview/submit-answer", json={"session_id": session_id, "answer": "hi"})
    feedback = await other_client.post("/api/interview/get-feedback", json={"session_id": session_id})
    assert detail.status_code == submit.status_code == feedback.status_code == 404
    assert (await other_client.get("/api/interview/history")).json() == []
