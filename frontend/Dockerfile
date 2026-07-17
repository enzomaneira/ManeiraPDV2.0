FROM node:20-alpine
WORKDIR /app
COPY package*.json ./

# Adicione estas duas linhas para aumentar o tempo de espera da rede
RUN npm config set fetch-retry-mintimeout 20000
RUN npm config set fetch-retry-maxtimeout 120000

RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]