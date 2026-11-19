FROM node:22-slim
WORKDIR /web
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY . .
EXPOSE 3001
CMD ["npm", "run", "dev", "--", "-p", "3001", "-H", "0.0.0.0"]
