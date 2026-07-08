# TalentRank — Engineering Brief
Project: Semantic resume-to-job matching and ranking service.
Tech stack: Python 3.13, sentence-transformers, faiss-cpu (IndexHNSWFlat/IndexIVFFlat), fastapi, uvicorn, pydantic, pandas, numpy, scikit-learn, pytest, Docker.
Models: bi-encoder: all-MiniLM-L6-v2; cross-encoder: ms-marco-MiniLM-L-6-v2.

RULES:
1. NEVER fabricate, hardcode, mock, estimate, or invent any metric, score, latency, or dataset statistic. 
2. Pin all dependency versions in requirements.txt.
3. Use type hints, docstrings, and keep modules small.
4. Read paths/params from config.py, no magic numbers.
5. Wait for user verification before moving to the next phase.