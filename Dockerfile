FROM node:22-slim

RUN sed -i 's/deb.debian.org/mirrors.cloud.tencent.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.cloud.tencent.com/g' /etc/apt/sources.list.d/debian.sources && \
    npm config set registry https://mirrors.cloud.tencent.com/npm/

RUN apt update && \
    apt install -y nginx curl git && \
    rm -rf /var/lib/apt/lists/*

RUN npm i -g openclaw@latest && \
    npm cache clean --force

RUN useradd -m -s /bin/bash linuxbrew
RUN su - linuxbrew -c 'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' && \
    rm -rf /home/linuxbrew/.cache
ENV PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"

WORKDIR /workspace
COPY openclaw.json start.sh ./
RUN chmod +x start.sh

EXPOSE 8686
CMD ["./start.sh"]
