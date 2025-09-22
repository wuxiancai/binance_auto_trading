import os

class Config:
    # 基本设置
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSDT")
    INTERVAL: str = os.getenv("INTERVAL", "1m")  # K线时间周期
    BOLL_PERIOD: int = int(os.getenv("BOLL_PERIOD", 20))
    BOLL_STD: float = float(os.getenv("BOLL_STD", 2.0))
    INITIAL_KLINES: int = int(os.getenv("INITIAL_KLINES", 50))

    # 交易相关
    QUANTITY: float = float(os.getenv("QUANTITY", 0.001))  # 下单数量（合约张数或币量, 根据交易对调整）
    LEVERAGE: int = int(os.getenv("LEVERAGE", 5))
    USE_TESTNET: bool = os.getenv("USE_TESTNET", "false").lower() == "true"
    SIMULATE: bool = os.getenv("SIMULATE", "true").lower() == "true"  # 模拟交易

    # API 密钥
    API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

    # 数据库与日志
    DB_PATH: str = os.getenv("DB_PATH", "data/trading.db")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # 自动重启
    AUTO_RESTART: bool = os.getenv("AUTO_RESTART", "true").lower() == "true"

    # Web 服务
    WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT: int = int(os.getenv("WEB_PORT", 5000))


config = Config()