FROM node:20-alpine

WORKDIR /app

# `npm ci` installs exactly what the lockfile says and fails if the lockfile
# and package.json disagree. `npm install` without a lockfile re-resolved every
# `^` range on each build, so the image that worked and the image you got next
# time were different builds of different versions, with nothing recording
# which ones had been tested.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 8311

CMD ["npm", "run", "dev"]
