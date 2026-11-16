FROM node:22-alpine

WORKDIR /app
ENV NODE_ENV=production

COPY package.json ./
COPY server.js ./
COPY api ./api
COPY openapi.json ./openapi.json
COPY implementation/patient-web ./implementation/patient-web

EXPOSE 8080
CMD ["node", "server.js"]
