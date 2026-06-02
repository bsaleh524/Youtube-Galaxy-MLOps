FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    streamlit>=1.35.0 \
    plotly>=5.20.0 \
    pandas>=2.0.0 \
    pyarrow>=14.0.0 \
    requests>=2.31.0

COPY streamlit_app.py .

EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
