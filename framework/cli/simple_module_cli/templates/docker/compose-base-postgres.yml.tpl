services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: "{{PG_DB}}"
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {{PG_DB}}"]
      interval: 5s
      timeout: 5s
      retries: 10

  app:
    build:
      context: .
      dockerfile: docker/host.Dockerfile
    env_file:
      - path: .env
        required: false
    environment:
      # Containers serve the built bundle; development mode would emit
      # asset tags pointing at the (absent) Vite dev server.
      SM_ENVIRONMENT: production
      SM_DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/{{PG_DB}}
{{APP_EXTRA_ENV}}    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
