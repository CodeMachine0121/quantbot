# quantbot/domain/values/cross_direction.py
from enum import StrEnum


class CrossDirection(StrEnum):
    """交叉往哪個方向。

    Day 04 講過這兩件事的俗名是黃金交叉與死亡交叉，而它們的定義是**狀態翻轉**：
    前一根還在下面、這一根到了上面。所以它是一個事件，只有翻轉的那一根成立，
    不是「整段站在上面」——後者是 Comparison.ABOVE，是完全不同的一個條件。

    新手最常寫錯的就是這一組。把「快線在慢線之上」當成交叉，一段趨勢裡每一根
    都會觸發進場，而回測會因為重複進場產生一條漂亮到不合理的權益曲線。
    """

    UP = "up"
    DOWN = "down"
