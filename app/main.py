from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth_router, banks_router, quiz_router, wrong_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Quiz Master API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(banks_router.router)
app.include_router(quiz_router.router)
app.include_router(wrong_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
