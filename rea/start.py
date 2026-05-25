"""Start the REA Communication Agent."""
import uvicorn
from rea.config import REA_HOST, REA_PORT

if __name__ == "__main__":
    uvicorn.run("rea.main:app", host=REA_HOST, port=REA_PORT, reload=False)
