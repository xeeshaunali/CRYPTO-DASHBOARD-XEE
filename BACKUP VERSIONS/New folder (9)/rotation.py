# rotation.py
import ccxt
import pandas as pd
from datetime import datetime
from statistics import mean

from indicators import add_all_indicators, generate_signal_summary

# Hardcoded use-case mapping (base symbols, without /USDT)
USE_CASES = {
    "AI": ["PHB", "AGIX", "FET", "ALI", "OCEAN", "RNDR", "INJ"],
    "LAYER1": ["SOL", "AVAX", "NEAR", "ATOM", "ALGO", "EGLD", "GLMR", "MOVR", "CFX", "SYS", "FTM"],
    "L2": ["MATIC", "OP", "ARB", "IMX", "LRC", "STRK"],
    "DEX_DEFI": ["UNI", "CAKE", "AAVE", "GMX", "CRV", "RUNE", "SUSHI", "1INCH"],
    "GAMING": ["GALA", "SAND", "MANA", "AXS", "ILV", "YGG"],
    "INFRA": ["ARPA", "RIF", "ANKR", "STRAX", "CTSI", "CELR", "WAXP"],
    "PRIVACY": ["SCRT", "XMR", "ZEC"],
    "ORACLE": ["LINK", "BAND"],
    "STORAGE": ["AR", "FIL", "SC"],
    "BNB CHAIN": ["THE", "SOLV", "JUV", "ATM", "SFP", "ASR", "PSG", "TUT", "1000CHEEMS", "D", "OG", "BIFI", "FORM", "BMT", "DEGO", "DODO", "BEL", "TWT", "ONT", "ID", "CGPT", "CTK", "HOOK", "MBOX", "BNB", "TLM", "FLOKI", "C98", "INJ", "SHELL", "GALA", "CAKE", "BANANAS31", "LISTA", "XVS", "COOKIE", "1000CAT", "MUBARAK", "TST"],
    "SOLANA TOKEN": ["IO", "TNSR", "PYTH", "ORCA", "GMT", "JTO", "RENDER", "LAYER", "PENGU", "ME", "FIDA", "BOME", "JUP", "RAY", "PNUT", "BONK", "WIF", "ACT", "W"],
    "RWA": ["POLYX", "ONDO", "SNX", "SYRUP", "RSR", "LUMIA", "DUSK", "TRU", "AVAX", "PLUME", "VET", "CHR", "EPIC", "ICP", "SKY", "OM", "INJ", "USUAL", "PENDLE"],
    "MEME": ["1000CAT", "SHIB", "TUT", "TRUMP", "AIXBT", "PENGU", "1000SATS", "ORDI", "BOME", "NEIRO", "PEPE", "FLOKI", "PNUT", "BONK", "TURBO", "DOGE", "DOGS", "MEME", "PEOPLE", "BANANAS31", "WIF", "1000CHEEMS", "1MBABYDOGE", "BROCCOLI714", "ACT", "MUBARAK", "TST"],
    "PAYMENTS": ["HUMA", "ACH", "PUNDIX", "UTK", "XRP", "XNO", "LTC", "BTC", "COTI", "BCH"],
    "AI": ["AWE", "IO", "SAHARA", "CGPT", "RLC", "WLD", "FET", "THETA", "PHA", "OPEN", "NEWT", "NIL", "GRT", "FLUX", "IQ", "AIXBT", "SHELL", "AI", "POND", "CHR", "MDT", "ADX", "NMR", "VIRTUAL", "COOKIE", "HOLO", "LPT", "TURBO", "PHB", "INJ", "VANA", "KAITO", "TAO", "NFP", "ACT"],
    "LAYER1 / LAYER2": ["SOMI", "PLUME", "GUN", "TON", "TRX", "STRAX", "KAVA", "KAIA", "REI", "SOPH", "IOTX", "DCR", "ETH", "WAXP", "SKL", "S", "XTZ", "RONIN", "HIVE", "A", "CKB", "KSM", "ATOM", "OPEN", "OSMO", "LUNC", "IOST", "QKC", "QTUM", "SXP", "HOT", "ARDR", "XRP", "NEO", "RIF", "NIL", "FLUX", "POLYX", "NXPC", "NTRN", "CHZ", "VANA", "STRK", "ICP", "ARK", "FLOW", "ZK", "ICX", "ZIL", "GNO", "OM", "POL", "ACA", "ENJ", "MOVR", "PHB", "CELR", "EGLD", "LSK", "XLM", "ASTR", "SYS", "ONT", "SCR", "ALGO", "DYM", "VET", "CHR", "VANRY", "MINA", "CFX", "AXL", "MANTA", "SCRT", "LUNA", "VIC", "SAGA", "ARPA", "PARTI", "WAN", "IOTA", "MOVE", "APT", "LUMIA", "THETA", "ADA", "INIT", "BNB", "KDA", "SOL", "SXT", "OP", "INJ", "STX", "ARB", "TAO", "AEVO", "GLMR", "NEAR", "IMX", "METIS", "CTSI", "CELO", "SEI", "HBAR", "BERA", "LINEA", "SUI", "OMNI", "DOT", "ONE", "ROSE", "AVAX", "BABY", "EPIC", "BB"],
    "METAVERSE": ["D", "MANA", "GHST", "SAND", "ILV", "VANRY", "MBOX", "AXS", "SLP", "HIGH", "TLM", "FLOKI", "ALICE", "PYR", "MAGIC"],
    "SEED": ["PROM", "SOMI", "DOLO", "CHESS", "PUMP", "HOLO", "GUN", "TOWNS", "FIS", "SOLV", "FLM", "HEI", "ATM", "JUV", "POND", "ASR", "VELODROME", "PSG", "THE", "ACE", "BAR", "TUT", "SOPH", "WLFI", "TRUMP", "C", "SAHARA", "1000CHEEMS", "ACX", "SYRUP", "SUPER", "SUN", "HMSTR", "RED", "MITO", "NEWT", "DF", "RONIN", "GNS", "FORM", "1MBABYDOGE", "KAITO", "XAI", "NIL", "STO", "NOT", "SIGN", "NXPC", "BIFI", "AUCTION", "PERP", "NTRN", "ATA", "PEOPLE", "VANA", "OG", "ACT", "DEGO", "ZK", "BMT", "HFT", "COW", "OM", "SPK", "GHST", "HYPER", "NFP", "DODO", "ME", "SCR", "AGLD", "TNSR", "WIF", "DYM", "CATI", "BEL", "WCT", "VANRY", "CGPT", "G", "BANANA", "PORTAL", "ERA", "AXL", "MANTA", "OPEN", "IO", "ONDO", "HOOK", "SLP", "MEME", "SAGA", "ID", "ORCA", "PROVE", "LA", "TURBO", "NEIRO", "PARTI", "MOVE", "PHA", "1000SATS", "RESOLV", "INIT", "PIXEL", "RDNT", "SXT", "LISTA", "DOGS", "STG", "TREE", "ALT", "FLOKI", "USUAL", "SYN", "ALICE", "ZRO", "BOME", "ANIME", "AEVO", "GPS", "SHELL", "PNUT", "CYBER", "BIGTIME", "HUMA", "METIS", "CETUS", "BANANAS31", "ORDI", "TRU", "MAGIC", "BERA", "COOKIE", "RPL", "AIXBT", "LINEA", "OMNI", "1000CAT", "BIO", "ZKC", "HAEDAL", "REZ", "LQTY", "HOME", "AI", "MUBARAK", "VIRTUAL", "LAYER", "KERNEL", "BABY", "EPIC", "BB", "KMNO", "DEXE", "TST", "AVNT", "BROCCOLI714"],
    "LAUNCH POOL": ["GUN", "TON", "FLM", "HEI", "ATM", "JUV", "KAIA", "ASR", "PSG", "THE", "ACE", "SOPH", "MAV", "CITY", "D", "HMSTR", "RED", "NEWT", "KAITO", "XAI", "SANTOS", "NIL", "STO", "NOT", "SIGN", "NXPC", "ATA", "VANA", "OG", "BMT", "HFT", "SPK", "PENDLE", "HYPER", "NFP", "DODO", "SCR", "CATI", "BEL", "WCT", "ENA", "BANANA", "PORTAL", "MANTA", "IO", "MBOX", "MEME", "SAGA", "PARTI", "HIGH", "CTK", "MOVE", "TLM", "RESOLV", "INIT", "PIXEL", "RDNT", "SXT", "DOGS", "ALT", "USUAL", "ALICE", "ANIME", "AEVO", "GPS", "SHELL", "CYBER", "HUMA", "BEAMX", "SEI", "BERA", "XVS", "LINEA", "SUI", "OMNI", "1000CAT", "BIO", "HAEDAL", "QI", "REZ", "HOME", "AI", "LAYER", "ETHFI", "PENGU"],
    "MEGA DROP": ["SOLV", "LISTA", "KERNEL", "BB"],
    "GAMING": ["VOXEL", "GUN", "A2Z", "ACE", "YGG", "WAXP", "D", "HMSTR", "RONIN", "FORM", "MANA", "XAI", "NOT", "NXPC", "ENJ", "GHST", "SAND", "AGLD", "CATI", "ILV", "PORTAL", "MBOX", "AXS", "SLP", "TLM", "PIXEL", "FLOKI", "ALICE", "PYR", "GALA", "SOLV", "LISTA", "KERNEL", "BB"],
    "DEFI": ["DOLO", "CHESS", "FIS", "SOLV", "FLM", "HEI", "KAVA", "JST", "KAIA", "NMR", "VELODROME", "THE", "IDEX", "WLFI", "MAV", "USTC", "BNT", "WAXP", "ACX", "AMP", "SYRUP", "SUPER", "DIA", "SUN", "OSMO", "SKY", "MITO", "YFI", "DF", "LUNC", "GNS", "ZRX", "RIF", "STO", "QUICK", "SPELL", "BIFI", "AUCTION", "PERP", "DEGO", "KNC", "FXS", "HFT", "UNI", "MLN", "COW", "SPK", "ACA", "PENDLE", "GHST", "DODO", "COMP", "ALCX", "UMA", "BEL", "FARM", "ENA", "BANANA", "ANKR", "MBOX", "AAVE", "LUNA", "1INCH", "RAY", "ORCA", "CVX", "SNX", "SUSHI", "FORTH", "LUMIA", "WOO", "RESOLV", "C98", "RDNT", "LISTA", "STG", "TREE", "USUAL", "SYN", "INJ", "LRC", "CAKE", "AEVO", "CETUS", "RUNE", "BAND", "TRU", "CELO", "CRV", "RPL", "RSR", "XVS", "JUP", "TRB", "GMX", "QI", "DYDX", "OGN", "REZ", "LQTY", "HOME", "JOE", "LAYER", "ETHFI", "LDO", "JTO", "KERNEL", "KMNO", "DEXE", "AVNT", "EIGEN"],
    "MONITORING": ["VOXEL", "FIS", "FLM", "MDT", "REI", "MBL", "IDEX", "FTT", "ARDR", "BIFI", "PERP", "ARK", "NKN", "JASMY", "PORTAL", "MOVE", "GPS", "AWE"],
    "LIQUID STAKING": ["WBETH", "LDO", "FXS", "ANKR", "RPL", "LISTA", "QI", "OGN", "haedal", "chess", "fis"],
    "FAN TOKEN": ["CHZ", "OG", "ALPINE", "SANTOS", "ASR", "PSG", "BAR", "JUV", "CITY", "PORTO", "LAZIO", "ATM", "ACM"],
    "INFRASTRUCTURE": ["LINK", "WLD", "ONDO", "RENDER", "FET", "TIA", "QNT", "GRT", "PYTH", "ENS", "THETA", "JASMY", "EIGEN", "ZRO", "W", "ZK", "PLUME", "AXL", "TWT", "LPT", "ARKM", "KAITO", "IOTX", "GLM", "BAT", "SFP", "ASTR", "DYM", "ID", "ALT", "PROVE", "T", "RED", "LAYER", "ZKC", "API3", "POLYX", "SSV", "IO", "MASK", "BAND", "SXT", "G", "ERA", "RLC", "SIGN", "TRB", "BICO", "CYBER", "FIDA", "CVC", "PHA", "DIA", "CGPT", "FLUX", "DENT", "POND", "LA", "MTL", "WCT", "HYPER", "OXT", "CTK", "WIN", "MAV", "PARTI", "ATA", "C", "GPS", "ARPA", "RAD", "GTC", "HEI", "DUSK", "BMT", "HOOK", "NKN", "DATA", "ADX", "MDT", "FIO"],
    "STORAGE": ["FIL", "STX", "BTTC", "AR", "HOT", "SC", "STORJ", "RIF"],
    "NFT": ["PENGU", "IMX", "GALA", "SAND", "FORM", "MANA", "APE", "CHZ", "AXS", "SUPER", "BLUR", "PROM", "GMT", "ENJ", "ME", "ANIME", "WAXP", "CHR", "AUDIO", "MAGIC", "SLP", "AGLD", "VANRY", "PYR", "TNSR", "RARE", "HIGH", "ALICE", "NFP", "MBOX", "DEGO", "D"],
    "LAUNCH PAD": ["FIO", "POL", "FET", "INJ", "SAND", "BTTC", "AXS", "EGLD", "KAVA", "ARKM", "SFP", "ID", "ONE", "GMT", "BAND", "EDU", "CTSI", "CELR", "C98", "A2Z", "ALPINE", "TKO", "HOOK", "DEGO", "VOXEL", "PORTO", "LAZIO"],
    "POLKADOT": ["DOT", "KSM", "ASTR", "PHA", "GLMR", "ATA", "ACA"],
    "POW": ["BTC", "DOGE", "BCH", "LTC", "ETC", "STX", "CFX", "ZEC", "IOTA", "DASH", "DCR", "CKB", "ZIL", "RVN", "SC", "ANKR", "DGB", "KDA", "ZEN", "ONT", "TRB", "XVG", "FLUX", "RIF", "QKC", "SYS", "NKN"],
    
    "AI": ["PHB", "AGIX", "FET", "ALI", "OCEAN", "RNDR", "INJ", "AWE", "IO", "SAHARA", "CGPT", "RLC", "WLD", "THETA", "PHA", "OPEN", "NEWT", "NIL", "GRT", "FLUX", "IQ", "AIXBT", "SHELL", "POND", "CHR", "MDT", "ADX", "NMR", "VIRTUAL", "COOKIE", "HOLO", "LPT", "TURBO", "VANA", "KAITO", "TAO", "NFP", "ACT", "ARKM", "TAO"],  # Decentralized AI compute, data marketplaces, agents, rendering (e.g., FET/AGIX/OCEAN merged into ASI ecosystem, RNDR for GPU, TAO for Bittensor)

    "MEME": ["1000CAT", "SHIB", "TUT", "TRUMP", "AIXBT", "PENGU", "1000SATS", "ORDI", "BOME", "NEIRO", "PEPE", "FLOKI", "PNUT", "BONK", "TURBO", "DOGE", "DOGS", "MEME", "PEOPLE", "BANANAS31", "WIF", "1000CHEEMS", "1MBABYDOGE", "BROCCOLI714", "ACT", "MUBARAK", "TST", "GOAT", "POPCAT"],  # Community/hype-driven, often Solana-based (e.g., BONK/WIF/PNUT/PENGU leading 2025 meme supercycle)

    "LAYER1": ["SOL", "AVAX", "NEAR", "ATOM", "ALGO", "EGLD", "GLMR", "MOVR", "CFX", "SYS", "FTM", "TON", "TRX", "KAVA", "KAIA", "REI", "SOPH", "IOTX", "DCR", "ETH", "SKL", "XTZ", "RONIN", "HIVE", "CKB", "KSM", "IOST", "QKC", "QTUM", "SXP", "HOT", "ARDR", "NEO", "CHZ", "ICX", "ZIL", "GNO", "ACA", "LSK", "XLM", "ASTR", "DYM", "MINA", "AXL", "MANTA", "WAN", "IOTA", "APT", "INIT", "BNB", "KDA", "SUI", "DOT", "HBAR", "ADA", "SEI", "CELO", "STX"],  # Base blockchains (e.g., SOL for high TPS/memes, AVAX for subnets/RWA)

    "LAYER2": ["MATIC", "OP", "ARB", "IMX", "LRC", "STRK", "METIS", "BERA", "LINEA", "OMNI", "ZK", "BASE", "SCROLL"],  # Scaling solutions on Ethereum/other L1s (e.g., ARB/OP for rollups)

    "DEFI_DEX": ["UNI", "CAKE", "AAVE", "GMX", "CRV", "RUNE", "SUSHI", "1INCH", "PENDLE", "JUP", "RAY", "ORCA", "SNX", "CVX", "LDO", "RPL", "LUNA", "FORTH", "WOO", "RDNT", "STG", "SYN", "JOE", "GMX", "DYDX", "PERP", "FXS", "COMP", "ALCX", "UMA", "YFI", "BAL", "KNC"],  # Lending, DEXs, perpetuals, yield (e.g., AAVE lending, UNI swaps, PENDLE yield trading)

    "RWA": ["ONDO", "POLYX", "SNX", "SYRUP", "RSR", "LUMIA", "DUSK", "TRU", "PLUME", "VET", "CHR", "OM", "INJ", "USUAL", "PENDLE", "MANTRA", "CLEARPOOL"],  # Real-world asset tokenization (e.g., ONDO for treasuries, PLUME for institutional)

    "GAMING_METAVERSE_NFT": ["GALA", "SAND", "MANA", "AXS", "ILV", "YGG", "VOXEL", "ENJ", "SLP", "HIGH", "TLM", "ALICE", "PYR", "MAGIC", "IMX", "APE", "BLUR", "GMT", "AUDIO", "RARE", "GHST", "AGLD", "PIXEL", "BIGTIME", "PORTAL", "CATI", "NOT", "XAI"],  # Play-to-earn, virtual worlds, NFTs (e.g., AXS for Axie, SAND for land)

    "ORACLE_INFRA": ["LINK", "BAND", "PYTH", "API3", "DIA", "ARPA", "ANKR", "CTSI", "CELR", "WAXP", "TWT", "BAND", "TRB", "BICO", "MASK", "SSV"],  # Data oracles, bridges, infrastructure (e.g., LINK for price feeds, PYTH for high-frequency)

    "STORAGE_DEPIN": ["FIL", "AR", "SC", "STORJ", "BTTC", "HOT", "RIF", "GLM", "AKT", "BZZ"],  # Decentralized storage/compute (e.g., FIL for Filecoin)

    "PRIVACY": ["SCRT", "XMR", "ZEC", "ROSE", "DUSK"],  # Privacy-focused chains/transactions

    "PAYMENTS_STABLE": ["XRP", "XNO", "LTC", "BTC", "COTI", "BCH", "ACH", "PUNDIX", "UTK", "HUMA", "USDT", "USDC"],  # Fast payments, cross-border (e.g., XRP for RippleNet)

    "LIQUID_STAKING": ["LDO", "RPL", "ANKR", "LISTA", "QI", "OGN", "WBETH", "STETH", "JTO"],  # Staking derivatives (e.g., LDO for Lido)

    "FAN_SPORTS": ["CHZ", "OG", "ALPINE", "SANTOS", "ASR", "PSG", "BAR", "JUV", "CITY", "PORTO", "LAZIO", "ATM", "ACM"],  # Fan tokens for sports clubs

    "POW_MINING": ["BTC", "DOGE", "BCH", "LTC", "ETC", "CFX", "ZEC", "IOTA", "DASH", "DCR", "CKB", "ZIL", "RVN", "DGB", "KDA", "ZEN", "XVG"],  # Proof-of-Work chains

    "BNB_SOL_ECO_MISC": ["THE", "SOLV", "JUV", "ATM", "SFP", "ASR", "PSG", "TUT", "BIFI", "FORM", "BMT", "DEGO", "DODO", "BEL", "TWT", "ONT", "ID", "CTK", "HOOK", "MBOX", "BANANAS31", "LISTA", "XVS", "COOKIE", "MUBARAK", "IO", "TNSR", "PYTH", "ORCA", "GMT", "JTO", "RENDER", "LAYER", "ME", "FIDA", "RAY", "W"]  # Ecosystem-specific (BNB Chain fans/utility, Solana tokens)

}


# Historical follower map: leaders -> typical followers
FOLLOW_MAP = {
    "GLMR": ["MOVR", "SYS", "CFX"],
    "CFX": ["GLMR", "SYS", "MOVR"],
    "PHB": ["FET", "AGIX", "OCEAN"],
    "GALA": ["SAND", "MANA"],
    "SYS": ["CFX", "GLMR"],
    "ACT": ["NIL", "SHELL", "NFP", "ALLO" ],
    "SXP": ["DENT", "WAN" ],
    "RESOLVE": ["RDNT", "BEL", "QI", "MAV", "DODO" ],
    "TST": ["TUT", "BROCCOLI714", "D", "HOOK" ],
    "ACT": ["NIL", "SHELL", "NFP", "ALLO" ],
    "NIL": ["MDT"],
    "SOPH": ["MBOX", "HIGH", "ALICE", "CATI" ],
    "SSV": ["IO", "RLC", "ARPA", "PHA" ],
    "CHZ": ["APE", "GALA", "ENJ", "ALLO" ],
    "ASR": ["ATM", "JUV", "PSG"],
    "AKT": ["ATM", "FIL", "AR", "STORJ", "SC", "RNDR"],
    
    "AI": ["PHB", "AGIX", "FET", "ALI", "OCEAN", "RNDR", "INJ", "AWE", "IO", "SAHARA", "CGPT", "RLC", "WLD", "THETA", "PHA", "OPEN", "NEWT", "NIL", "GRT", "FLUX", "IQ", "AIXBT", "SHELL", "POND", "CHR", "MDT", "ADX", "NMR", "VIRTUAL", "COOKIE", "HOLO", "LPT", "TURBO", "VANA", "KAITO", "TAO", "NFP", "ACT", "ARKM", "TAO"],  # Decentralized AI compute, data marketplaces, agents, rendering (e.g., FET/AGIX/OCEAN merged into ASI ecosystem, RNDR for GPU, TAO for Bittensor)

    "MEME": ["1000CAT", "SHIB", "TUT", "TRUMP", "AIXBT", "PENGU", "1000SATS", "ORDI", "BOME", "NEIRO", "PEPE", "FLOKI", "PNUT", "BONK", "TURBO", "DOGE", "DOGS", "MEME", "PEOPLE", "BANANAS31", "WIF", "1000CHEEMS", "1MBABYDOGE", "BROCCOLI714", "ACT", "MUBARAK", "TST", "GOAT", "POPCAT"],  # Community/hype-driven, often Solana-based (e.g., BONK/WIF/PNUT/PENGU leading 2025 meme supercycle)

    "LAYER1": ["SOL", "AVAX", "NEAR", "ATOM", "ALGO", "EGLD", "GLMR", "MOVR", "CFX", "SYS", "FTM", "TON", "TRX", "KAVA", "KAIA", "REI", "SOPH", "IOTX", "DCR", "ETH", "SKL", "XTZ", "RONIN", "HIVE", "CKB", "KSM", "IOST", "QKC", "QTUM", "SXP", "HOT", "ARDR", "NEO", "CHZ", "ICX", "ZIL", "GNO", "ACA", "LSK", "XLM", "ASTR", "DYM", "MINA", "AXL", "MANTA", "WAN", "IOTA", "APT", "INIT", "BNB", "KDA", "SUI", "DOT", "HBAR", "ADA", "SEI", "CELO", "STX"],  # Base blockchains (e.g., SOL for high TPS/memes, AVAX for subnets/RWA)

    "LAYER2": ["MATIC", "OP", "ARB", "IMX", "LRC", "STRK", "METIS", "BERA", "LINEA", "OMNI", "ZK", "BASE", "SCROLL"],  # Scaling solutions on Ethereum/other L1s (e.g., ARB/OP for rollups)

    "DEFI_DEX": ["UNI", "CAKE", "AAVE", "GMX", "CRV", "RUNE", "SUSHI", "1INCH", "PENDLE", "JUP", "RAY", "ORCA", "SNX", "CVX", "LDO", "RPL", "LUNA", "FORTH", "WOO", "RDNT", "STG", "SYN", "JOE", "GMX", "DYDX", "PERP", "FXS", "COMP", "ALCX", "UMA", "YFI", "BAL", "KNC"],  # Lending, DEXs, perpetuals, yield (e.g., AAVE lending, UNI swaps, PENDLE yield trading)

    "RWA": ["ONDO", "POLYX", "SNX", "SYRUP", "RSR", "LUMIA", "DUSK", "TRU", "PLUME", "VET", "CHR", "OM", "INJ", "USUAL", "PENDLE", "MANTRA", "CLEARPOOL"],  # Real-world asset tokenization (e.g., ONDO for treasuries, PLUME for institutional)

    "GAMING_METAVERSE_NFT": ["GALA", "SAND", "MANA", "AXS", "ILV", "YGG", "VOXEL", "ENJ", "SLP", "HIGH", "TLM", "ALICE", "PYR", "MAGIC", "IMX", "APE", "BLUR", "GMT", "AUDIO", "RARE", "GHST", "AGLD", "PIXEL", "BIGTIME", "PORTAL", "CATI", "NOT", "XAI"],  # Play-to-earn, virtual worlds, NFTs (e.g., AXS for Axie, SAND for land)

    "ORACLE_INFRA": ["LINK", "BAND", "PYTH", "API3", "DIA", "ARPA", "ANKR", "CTSI", "CELR", "WAXP", "TWT", "BAND", "TRB", "BICO", "MASK", "SSV"],  # Data oracles, bridges, infrastructure (e.g., LINK for price feeds, PYTH for high-frequency)

    "STORAGE_DEPIN": ["FIL", "AR", "SC", "STORJ", "BTTC", "HOT", "RIF", "GLM", "AKT", "BZZ"],  # Decentralized storage/compute (e.g., FIL for Filecoin)

    "PRIVACY": ["SCRT", "XMR", "ZEC", "ROSE", "DUSK"],  # Privacy-focused chains/transactions

    "PAYMENTS_STABLE": ["XRP", "XNO", "LTC", "BTC", "COTI", "BCH", "ACH", "PUNDIX", "UTK", "HUMA", "USDT", "USDC"],  # Fast payments, cross-border (e.g., XRP for RippleNet)

    "LIQUID_STAKING": ["LDO", "RPL", "ANKR", "LISTA", "QI", "OGN", "WBETH", "STETH", "JTO"],  # Staking derivatives (e.g., LDO for Lido)

    "FAN_SPORTS": ["CHZ", "OG", "ALPINE", "SANTOS", "ASR", "PSG", "BAR", "JUV", "CITY", "PORTO", "LAZIO", "ATM", "ACM"],  # Fan tokens for sports clubs

    "POW_MINING": ["BTC", "DOGE", "BCH", "LTC", "ETC", "CFX", "ZEC", "IOTA", "DASH", "DCR", "CKB", "ZIL", "RVN", "DGB", "KDA", "ZEN", "XVG"],  # Proof-of-Work chains

    "BNB_SOL_ECO_MISC": ["THE", "SOLV", "JUV", "ATM", "SFP", "ASR", "PSG", "TUT", "BIFI", "FORM", "BMT", "DEGO", "DODO", "BEL", "TWT", "ONT", "ID", "CTK", "HOOK", "MBOX", "BANANAS31", "LISTA", "XVS", "COOKIE", "MUBARAK", "IO", "TNSR", "PYTH", "ORCA", "GMT", "JTO", "RENDER", "LAYER", "ME", "FIDA", "RAY", "W"] , # Ecosystem-specific (BNB Chain fans/utility, Solana tokens)

}

# Quick reverse lookup: base -> category
BASE_TO_CATEGORY = {}
for cat, coins in USE_CASES.items():
    for b in coins:
        BASE_TO_CATEGORY[b] = cat

# Pump score threshold (Option 2 = 50)
PUMP_SCORE_THRESHOLD = 50


def get_base(symbol: str) -> str:
    """Convert 'PHB/USDT' -> 'PHB'."""
    if "/" in symbol:
        return symbol.split("/")[0]
    if symbol.endswith("USDT"):
        return symbol.replace("USDT", "")
    return symbol


def compute_sector_strength(pumped_rows_for_cat):
    """
    Compute a 0–100 sector strength score based on:
    - avg % change
    - number of pumped coins
    - avg volume (log scaled)
    """
    if not pumped_rows_for_cat:
        return 0.0

    pct_changes = [float(r["price_change_percent"]) for r in pumped_rows_for_cat]
    vols = [float(r["volume_24h"]) for r in pumped_rows_for_cat if r["volume_24h"]]

    avg_pct = mean(pct_changes) if pct_changes else 0.0
    count = len(pumped_rows_for_cat)

    # Normalize pct: 0..30% -> 0..40 score (cap)
    pct_score = max(0.0, min(40.0, avg_pct * (40.0 / 30.0)))  # 30% avg -> 40 points

    # Breadth: 1 coin -> 10, 2->20, 3+ -> 30
    if count >= 3:
        breadth_score = 30.0
    elif count == 2:
        breadth_score = 20.0
    else:
        breadth_score = 10.0

    # Volume score (log10)
    if vols:
        avg_vol = mean(vols)
        # log scale 1e6..1e10 -> 0..30 approx
        import math
        lv = math.log10(max(avg_vol, 1))
        volume_score = max(0.0, min(30.0, (lv - 5) * 7.5))  # rough mapping
    else:
        volume_score = 0.0

    sector_strength = pct_score + breadth_score + volume_score
    # Clamp to 0–100
    return max(0.0, min(100.0, sector_strength))


def compute_multi_timeframe_score(exchange, symbol: str):
    """
    Check 1h / 4h / 1d trends using the indicator engine.
    Returns 0–100 score.
    """
    timeframes = ["1h", "4h", "1d"]
    scores = []

    for tf in timeframes:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=200)
            if not ohlcv:
                continue
            df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
            df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
            df_ind = add_all_indicators(df)
            sig = generate_signal_summary(df_ind)
            scores.append(sig["score"])
        except Exception:
            continue

    if not scores:
        return 0.0

    # Simple average of TF scores
    mf_score = mean(scores)
    return max(0.0, min(100.0, mf_score))


def follower_boost(leader_base: str, candidate_base: str) -> float:
    """
    If candidate historically follows leader, return extra boost.
    """
    followers = FOLLOW_MAP.get(leader_base, [])
    if candidate_base in followers:
        return 10.0
    return 0.0


def get_rotation_candidates_from_gainers(gainers_rows, max_per_category=5):
    """
    gainers_rows: list of dicts from DB (symbol, price_change_percent, volume_24h)
    Returns:
    [
      {
        "pumped_symbol": "PHB/USDT",
        "pumped_category": "AI",
        "pumped_change_pct": 12.3,
        "pumped_volume": 12345678,
        "sector_strength": 81.2,
        "rotation_candidates": [
            {
              "symbol": "AGIX/USDT",
              "category": "AI",
              "today_change_pct": 3.1,
              "today_volume": 1234567,
              "close": 0.1234,
              "readiness_score": 84,
              "sector_strength": 81.2,
              "multi_tf_score": 74.5,
              "follower_boost": 10,
              "pump_score": 83,
              "score": 83,          # alias for front-end
              "label": "STRONG_BULLISH",
              "bias": "bullish",
              "rsi": 48.7
            },
            ...
        ]
      },
      ...
    ]
    """
    ex = ccxt.binance({"enableRateLimit": True})
    tickers = ex.fetch_tickers()

    # --- Pre-compute sector strength per category based on pumped coins ---
    cat_to_pumped_rows = {}
    for row in gainers_rows:
        pumped_symbol = row["symbol"]
        pumped_base = get_base(pumped_symbol)
        cat = BASE_TO_CATEGORY.get(pumped_base)
        if not cat:
            continue
        cat_to_pumped_rows.setdefault(cat, []).append(row)

    cat_to_strength = {
        cat: compute_sector_strength(rows)
        for cat, rows in cat_to_pumped_rows.items()
    }

    results = []

    # For each pumped coin, build rotation candidates
    for row in gainers_rows:
        pumped_symbol = row["symbol"]
        pumped_base = get_base(pumped_symbol)
        category = BASE_TO_CATEGORY.get(pumped_base)
        if not category:
            continue  # skip unmapped

        pumped_change = float(row["price_change_percent"])
        pumped_vol = float(row["volume_24h"])
        sector_strength = cat_to_strength.get(category, 0.0)

        # Use-case coins in same category
        same_cat_bases = USE_CASES.get(category, [])
        if not same_cat_bases:
            continue

        candidates_meta = []

        for base in same_cat_bases:
            if base == pumped_base:
                continue
            sym = f"{base}/USDT"
            t = tickers.get(sym)
            if not t:
                continue

            pct = t.get("percentage")
            vol = t.get("quoteVolume")
            last = t.get("last")
            if pct is None or vol is None or last is None:
                continue

            pct = float(pct)
            vol = float(vol)

            # Filter basic rotation conditions:
            # - similar/smaller size than leader
            # - not already pumped hard (we want laggards)
            # - some minimum liquidity
            if vol <= pumped_vol * 1.2 and pct < 10.0 and vol > 100000:
                candidates_meta.append({
                    "symbol": sym,
                    "base": base,
                    "pct": pct,
                    "vol": vol,
                    "last": float(last)
                })

        # If no same-category candidates -> skip
        if not candidates_meta:
            continue

        rotation_candidates = []

        for c in candidates_meta:
            sym = c["symbol"]
            base = c["base"]

            try:
                # 4h main timeframe analysis
                ohlcv = ex.fetch_ohlcv(sym, timeframe="4h", limit=200)
                if not ohlcv:
                    continue
                df = pd.DataFrame(ohlcv, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                df["Time (UTC)"] = pd.to_datetime(df["Timestamp"], unit="ms")
                df_ind = add_all_indicators(df)
                sig = generate_signal_summary(df_ind)

                readiness_score = sig["score"]  # main TF signal score
                mf_score = compute_multi_timeframe_score(ex, sym)
                fb = follower_boost(pumped_base, base)

                # Combined pump probability score
                pump_score = (
                    0.45 * readiness_score +
                    0.35 * sector_strength +
                    0.15 * mf_score +
                    0.05 * fb
                )
                pump_score = max(0.0, min(100.0, pump_score))

                # Apply global threshold (>= 50)
                if pump_score < PUMP_SCORE_THRESHOLD:
                    continue

                rotation_candidates.append({
                    "symbol": sym,
                    "category": category,
                    "today_change_pct": c["pct"],
                    "today_volume": c["vol"],
                    "close": sig["close"],
                    "readiness_score": round(readiness_score, 1),
                    "sector_strength": round(sector_strength, 1),
                    "multi_tf_score": round(mf_score, 1),
                    "follower_boost": round(fb, 1),
                    "pump_score": round(pump_score, 1),
                    "score": round(pump_score, 1),  # alias for front-end
                    "label": sig["label"],
                    "bias": sig["bias"],
                    "rsi": sig["rsi"],
                })

            except Exception:
                # Skip any failures quietly; rotation is best-effort
                continue

        if rotation_candidates:
            # Sort all candidates for this pumped coin by pump_score desc
            rotation_candidates.sort(key=lambda x: x["pump_score"], reverse=True)

            results.append({
                "pumped_symbol": pumped_symbol,
                "pumped_category": category,
                "pumped_change_pct": pumped_change,
                "pumped_volume": pumped_vol,
                "sector_strength": round(sector_strength, 1),
                "rotation_candidates": rotation_candidates
            })

    return results
