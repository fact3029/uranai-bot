"""タロット（大アルカナ22枚）。カードを引くのはコード側の乱数で、AIには引いた結果だけを渡す。"""
import random
from dataclasses import dataclass

# (名前, 正位置の意味, 逆位置の意味)
MAJOR_ARCANA = [
    ("愚者", "自由・新しい始まり・冒険", "無計画・軽率・迷い"),
    ("魔術師", "創造・行動力・才能の発揮", "空回り・準備不足・ごまかし"),
    ("女教皇", "直感・知性・静かな洞察", "神経質・閉鎖的・思い込み"),
    ("女帝", "豊かさ・愛情・実り", "過保護・怠惰・浪費"),
    ("皇帝", "安定・責任・リーダーシップ", "独断・頑固・支配"),
    ("教皇", "信頼・助言・伝統", "形式主義・孤立・不信"),
    ("恋人", "選択・調和・惹かれ合い", "迷い・すれ違い・誘惑"),
    ("戦車", "前進・勝利・意志の強さ", "暴走・焦り・方向転換"),
    ("力", "忍耐・内なる強さ・優しさ", "自信喪失・無理・感情的"),
    ("隠者", "内省・探求・一人の時間", "孤独・閉じこもり・頑なさ"),
    ("運命の輪", "転機・チャンス・流れに乗る", "タイミングのずれ・停滞"),
    ("正義", "公正・バランス・決断", "不公平・優柔不断・偏り"),
    ("吊るされた男", "忍耐・視点の転換・待つ時", "徒労・自己犠牲・停滞"),
    ("死神", "終わりと再生・切り替え", "変化への抵抗・未練"),
    ("節制", "調和・節度・ゆるやかな回復", "不均衡・やりすぎ・散漫"),
    ("悪魔", "執着・誘惑・本音の欲求", "解放・悪習を断つ"),
    ("塔", "急な変化・気づき・崩壊と再構築", "小さな混乱・変化の予兆"),
    ("星", "希望・ひらめき・癒し", "失望・高望み・自信の揺らぎ"),
    ("月", "不安・曖昧さ・潜在意識", "霧が晴れる・誤解が解ける"),
    ("太陽", "成功・喜び・活力", "空元気・一時的な停滞"),
    ("審判", "復活・決断・呼びかけに応える", "後悔・踏み切れない"),
    ("世界", "完成・達成・新しいステージ", "あと一歩・未完成"),
]

# レア度は見た目の演出だけで、運勢の良し悪しとは関係ない。確率は画面にも表示する。
RARITIES = [("UR", 0.01), ("SSR", 0.04), ("SR", 0.15), ("R", 0.30), ("N", 0.50)]


def roll_rarity(rng: random.Random) -> str:
    x = rng.random()
    for name, p in RARITIES:
        if x < p:
            return name
        x -= p
    return "N"


SPREAD_POSITIONS = {
    1: ["今日のあなた"],
    3: ["過去", "現在", "未来"],
}


@dataclass(frozen=True)
class DrawnCard:
    position: str
    name: str
    reversed: bool
    meaning: str
    rarity: str = "N"

    @property
    def label(self) -> str:
        return f"{self.name}（{'逆位置' if self.reversed else '正位置'}）"


def draw(count: int = 1, rng: random.Random | None = None) -> list[DrawnCard]:
    if count not in SPREAD_POSITIONS:
        raise ValueError("count must be 1 or 3")
    rng = rng or random.SystemRandom()
    picks = rng.sample(MAJOR_ARCANA, count)
    cards = []
    for position, (name, up, down) in zip(SPREAD_POSITIONS[count], picks):
        rev = rng.random() < 0.5
        cards.append(DrawnCard(position, name, rev, down if rev else up, roll_rarity(rng)))
    return cards
