from fastapi import FastAPI

app = FastAPI(title="AI Interview Assistant")


@app.get("/health")
async def health():
    return {"status": "ok"}
