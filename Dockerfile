FROM langchain/langgraph-api:3.13-wolfi

# -- Adding local package . --
ADD . /deps/deploy-langgraph-server-auth
# -- End of local package . --

# -- Copy server infrastructure (includes configuration) --
COPY server/ /api/server/
COPY scripts/ /api/scripts/
# -- End of server setup --

# -- Installing all local dependencies --
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir -c /api/constraints.txt -e /deps/*
# -- End of local dependencies install --

# Point the wrapper to the Country Profiles agent
ENV LANGSERVE_GRAPHS='{"country_profiles": "/deps/deploy-langgraph-server-auth/src/country_profiles/internal_researcher.py:graph"}'

ENV PYTHONPATH="/deps/deploy-langgraph-server-auth:/api"

# -- Ensure user deps didn't inadvertently overwrite langgraph-api
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && \
    touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api
# -- End of ensuring user deps didn't inadvertently overwrite langgraph-api --

# -- Removing pip from the final image to keep it lightweight --
RUN pip uninstall -y pip setuptools wheel && \
    rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* && \
    find /usr/local/bin -name "pip*" -delete || true

# pip removal for wolfi
RUN rm -rf /usr/lib/python*/site-packages/pip* /usr/lib/python*/site-packages/setuptools* /usr/lib/python*/site-packages/wheel* && \
    find /usr/bin -name "pip*" -delete || true
RUN uv pip uninstall --system pip setuptools wheel && rm /usr/bin/uv /usr/bin/uvx
# -- End of pip removal --

WORKDIR /deps/deploy-langgraph-server-auth

# -- Use the modular proxy server that adds auth without modifying LangGraph --
ENTRYPOINT ["python", "/api/server/server_proxy.py"]