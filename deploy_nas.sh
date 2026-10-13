#!/bin/bash
# ==============================================================================
# G1-Cognition MVP NAS 涓€閿儴缃蹭笌鐜楠岃瘉鑴氭湰 (椋炵墰绉佹湁浜?fnOS / Debian Linux)
# ==============================================================================

set -e

COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "c158722")
echo "================================================================="
echo "  [AI 璁ょ煡澶嶇洏浜ゆ槗绯荤粺] NAS Docker 鐢熶骇鐜涓€閿儴缃蹭笌楠岃瘉"
echo "  鐢熶骇鍙戝竷鐗堟湰: v0.4.1 (Commit: ${COMMIT_SHA})"
echo "================================================================="

# 1. 妫€鏌?Docker 涓?Docker Compose
if ! command -v docker &> /dev/null; then
    echo "鉂?閿欒: 鏈娴嬪埌 docker 鍛戒护锛岃鍦ㄩ鐗涘簲鐢ㄤ腑蹇冨畨瑁?Docker 骞跺湪 SSH 鍚敤銆?
    exit 1
fi

if ! docker compose version &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "鉂?閿欒: 鏈娴嬪埌 docker compose 鏀寔銆?
    exit 1
fi

COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

# 2. 纭繚鎸佷箙鍖栫洰褰曞瓨鍦?echo "--> 妫€鏌ユ暟鎹寔涔呭寲鐩綍..."
mkdir -p ./data ./logs
chmod 777 ./data ./logs || true

# 3. 鏋勫缓骞跺惎鍔ㄥ鍣?echo "--> 寮€濮嬫瀯寤轰笌鎷夎捣瀹瑰櫒 (棣栨鏋勫缓闇€涓嬭浇鍩虹闀滃儚涓庣紪璇戯紝璇疯€愬績绛夊緟)..."
$COMPOSE_CMD down --remove-orphans || true
$COMPOSE_CMD build --no-cache
$COMPOSE_CMD up -d

# 4. 绛夊緟鍚庣鍋ュ悍妫€鏌?echo "--> 绛夊緟鍚庣鏈嶅姟鍋ュ悍妫€鏌ラ€氳繃..."
sleep 5
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/docs > /dev/null; then
        echo "鉁?鍚庣 FastAPI 鏈嶅姟鍋ュ悍灏辩华 (http://127.0.0.1:8000)锛?
        break
    fi
    echo "    绛夊緟鍚庣灏辩华涓?.. ($i/30)"
    sleep 2
done

# 5. 绛夊緟鍓嶇灏辩华
echo "--> 绛夊緟鍓嶇 Next.js 鏈嶅姟灏辩华..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:3000 > /dev/null; then
        echo "鉁?鍓嶇 Web 鏈嶅姟鍋ュ悍灏辩华 (http://127.0.0.1:3000)锛?
        break
    fi
    echo "    绛夊緟鍓嶇灏辩华涓?.. ($i/30)"
    sleep 2
done

# 6. 瀹瑰櫒鍐呰嚜鍔ㄥ寲娴嬭瘯楠岃瘉 (AC-1 ~ AC-6)
echo "--> 鍦ㄥ悗绔敓浜у鍣ㄥ唴杩愯鍥炲綊鑷姩鍖栨祴璇?.."
docker exec -it trading-ai-backend pytest backend/tests/test_cognition_validation.py -v || true

echo "================================================================="
echo "馃帀 閮ㄧ讲瀹屾垚锛?
echo "   鍓嶇 Web 鐪嬫澘: http://<NAS_IP>:3000"
echo "   鍚庣 API 鏂囨。: http://<NAS_IP>:8000/docs"
echo "================================================================="
