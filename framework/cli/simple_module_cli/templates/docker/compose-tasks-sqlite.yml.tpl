
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  # worker/beat reuse the app image — same code, different command. They
  # share the app's SQLite volume; WAL handles the modest concurrency, but
  # move to --db postgres if the task volume grows.
  worker:
    build:
      context: .
      dockerfile: docker/host.Dockerfile
    env_file:
      - path: .env
        required: false
    environment:
      SM_ENVIRONMENT: production
      SM_DATABASE_URL: sqlite+aiosqlite:////app/data/app.db
      SM_BG_TASKS_BROKER_URL: redis://redis:6379/0
      SM_BG_TASKS_RESULT_BACKEND: redis://redis:6379/1
    working_dir: /app
    volumes:
      - appdata:/app/data
    depends_on:
      redis:
        condition: service_healthy
    command:
      - "celery"
      - "-A"
      - "scripts.run_worker:celery"
      - "worker"
      - "-l"
      - "info"
      - "--concurrency=4"

  beat:
    build:
      context: .
      dockerfile: docker/host.Dockerfile
    env_file:
      - path: .env
        required: false
    environment:
      SM_ENVIRONMENT: production
      SM_DATABASE_URL: sqlite+aiosqlite:////app/data/app.db
      SM_BG_TASKS_BROKER_URL: redis://redis:6379/0
      SM_BG_TASKS_RESULT_BACKEND: redis://redis:6379/1
    working_dir: /app
    volumes:
      - appdata:/app/data
    depends_on:
      redis:
        condition: service_healthy
      worker:
        condition: service_started
    command:
      - "celery"
      - "-A"
      - "scripts.run_worker:celery"
      - "beat"
      - "-l"
      - "info"
