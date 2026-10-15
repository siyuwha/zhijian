# 构建阶段
ARG BASE_IMAGE=node:20-alpine
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_GIT_COMMIT=""
ARG NEXT_PUBLIC_BUILD_DATE=""
ENV NEXT_PUBLIC_GIT_COMMIT=$NEXT_PUBLIC_GIT_COMMIT
ENV NEXT_PUBLIC_BUILD_DATE=$NEXT_PUBLIC_BUILD_DATE

# 编译 Next.js 生产静态构建
RUN npm run build

# 生产运行阶段
FROM ${BASE_IMAGE} AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME="0.0.0.0" \
    TZ=Asia/Shanghai

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next

EXPOSE 3000

CMD ["npm", "start"]
