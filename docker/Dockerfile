FROM python:3.11-slim

# Evita prompt interativo
ENV DEBIAN_FRONTEND=noninteractive

# Instala dependências básicas
RUN apt-get update && apt-get install -y \
    sshpass \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala Ansible
RUN pip install ansible

# Define diretório de trabalho
WORKDIR /ansible

# Mantém container ativo
CMD ["sleep", "infinity"]
