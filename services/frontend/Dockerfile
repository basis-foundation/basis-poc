FROM node:20-alpine

WORKDIR /app

# Install dependencies (layer cached unless package.json changes)
COPY package*.json ./
RUN npm install

# Copy source (overridden by volume mount in development)
COPY . .

EXPOSE 5173

# --host 0.0.0.0 makes Vite reachable from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
