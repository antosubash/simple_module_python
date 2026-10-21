services:
  worker-{{NAME}}:
{{BODY}}    command:
      - "celery"
      - "-A"
      - "scripts.run_worker:celery"
      - "worker"
      - "-l"
      - "info"
      - "--concurrency=4"
      - "-Q"
      - "{{QUEUES}}"
