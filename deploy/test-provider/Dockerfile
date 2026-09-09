FROM python:3.13.7-slim
WORKDIR /opt/provider
RUN addgroup --system provider && adduser --system --ingroup provider --home /nonexistent provider
COPY deploy/test-provider/server.py /opt/provider/server.py
USER provider
EXPOSE 8090
CMD ["python", "/opt/provider/server.py"]
