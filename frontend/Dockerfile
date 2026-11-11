# Development image. Source is bind-mounted at /app; node_modules stays in the image
# (an anonymous volume in docker-compose.yml keeps the host folder from hiding it).
FROM node:26-alpine

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
