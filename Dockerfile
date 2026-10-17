# Base image: a small Linux with Python preinstalled
FROM python:3.12-slim

WORKDIR /app

# 1) CPU-only PyTorch first. sentence-transformers needs torch; the default
#    build bundles GPU libraries (~2 GB) that we don't need.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 2) Install dependencies BEFORE copying code. Docker caches each step as a
#    "layer", so editing your code later won't reinstall every package.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Download the embedding model now and bake it into the image,
#    so the first start doesn't wait on a download.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 4) Now copy the code (this layer changes often, so it comes last)
COPY . .

# Windows saves text files with CRLF line endings, which breaks shell scripts on Linux.
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh

EXPOSE 8501
ENTRYPOINT ["docker/entrypoint.sh"]