# quantbot/domain/values/activity_baseline.py
from enum import StrEnum


class ActivityBaseline(StrEnum):
    """「比平常熱」的平常，是拿什麼當基準。

    - ROLLING：跟自己最近 N 根比。它抓的是**相對於近期的異常**，所以在亞洲時段
      的凌晨，只要比同樣冷清的前幾小時熱，它就會給高分。
    - HOUR_OF_DAY：跟**同一個鐘點的歷史**比。加密貨幣 24/7 不休市，但它仍然有很
      明顯的時段節奏（歐美時段開始的那幾個小時成交量是亞洲深夜的好幾倍）。要問
      「現在真的不尋常嗎」，就得跟同一個鐘點比，不是跟三小時前比。

    兩個都要有，因為它們回答不同的問題。而 HOUR_OF_DAY 有一個很容易踩到的陷阱：
    用整段樣本算每個鐘點的平均，會把未來的資料算進基準裡。那是未來函數，
    而且它在回測上特別會騙人。實作用的是逐步展開的基準，見 TradingActivity。
    """

    ROLLING = "rolling"
    HOUR_OF_DAY = "hour_of_day"
