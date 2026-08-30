"""浣庝环鎻愰啋 + 寰俊鎺ㄩ€侊紙甯﹀幓鎶栵級"""
import logging
from typing import List, Optional

from .models import FlightPrice, Route


class Alerter:
    def __init__(self, logger: logging.Logger, notifier=None, storage=None,
                 push_drop_min: float = 30, push_rise_min: float = 50):
        """
        notifier:        鎺ㄩ€佸櫒锛圢one 琛ㄧず涓嶆帹閫侊級
        storage:         鐢ㄤ簬璇诲啓 alert_state锛堝幓鎶栵級
        push_drop_min:   瑙﹀彂"鍐嶆鎺ㄩ€?鐨勬渶灏忛檷骞?楼)
        push_rise_min:   瑙﹀彂"鍐嶆鎺ㄩ€?鐨勬渶灏忔定骞?楼)
        """
        self.logger = logger
        self.notifier = notifier
        self.storage = storage
        self.push_drop_min = push_drop_min
        self.push_rise_min = push_rise_min

    def check_and_alert(self, route: Route, prices: List[FlightPrice]):
        if not prices:
            return
        # 鎺у埗鍙?鏃ュ織锛氫笁骞冲彴瀵规瘮 + 澶氭棩鏈熷姣?
        self._compare_platforms(route, prices)
        self._compare_dates(route, prices)

        # 浣庝环闃堝€兼彁閱?
        if route.alert_threshold and route.alert_threshold > 0:
            self._handle_threshold(route, prices)
        else:
            self.logger.info(
                "[浣庝环] %s->%s threshold is 0; WeChat notifications disabled",
                route.from_name, route.to_name,
            )

    # ---------- 鎺у埗鍙板姣?----------
    def _compare_platforms(self, route: Route, prices: List[FlightPrice]):
        by_date = {}
        for p in prices:
            by_date.setdefault(p.depart_date, []).append(p)
        for date, lst in sorted(by_date.items()):
            lst = sorted(lst, key=lambda x: x.price)
            best = lst[0]
            line = " | ".join(f"{p.platform}: 楼{p.price:.0f}" for p in lst)
            self.logger.info(
                "[瀵规瘮] %s->%s %s 鏈€浣?%s 楼%.0f  (%s)",
                route.from_name, route.to_name, date,
                best.platform, best.price, line,
            )

    def _compare_dates(self, route: Route, prices: List[FlightPrice]):
        if len(route.dates) <= 1:
            return
        best_by_date = {}
        for p in prices:
            cur = best_by_date.get(p.depart_date)
            if cur is None or p.price < cur.price:
                best_by_date[p.depart_date] = p
        ordered = sorted(best_by_date.items(), key=lambda kv: kv[1].price)
        if not ordered:
            return
        cheapest_date, cheapest_p = ordered[0]
        self.logger.info(
            "[澶氭棩鏈焆 %s->%s 鏈€渚垮疁鏃ユ湡=%s 楼%.0f (%s)",
            route.from_name, route.to_name, cheapest_date,
            cheapest_p.price, cheapest_p.platform,
        )

    # ---------- 闃堝€兼彁閱?+ 鎺ㄩ€?----------
    def _handle_threshold(self, route: Route, prices: List[FlightPrice]):
        # 鎸夋棩鏈熷彇鏈€浣?
        best_by_date = {}
        for p in prices:
            cur = best_by_date.get(p.depart_date)
            if cur is None or p.price < cur.price:
                best_by_date[p.depart_date] = p

        for date, bp in sorted(best_by_date.items()):
            route_key = f"{route.from_code}-{route.to_code}-{date}"

            if bp.price > route.alert_threshold:
                # 娑ㄥ嚭闃堝€硷細娓呴櫎鍘绘姈鐘舵€侊紝涓嬫璺岀牬鎸?棣栨"閲嶆柊鎺?
                if self.storage:
                    self.storage.clear_alert_state(route_key)
                continue

            last = self.storage.get_alert_state(route_key) if self.storage else None
            should_push, reason = self._should_push(bp.price, last)

            # 鎺у埗鍙板缁堟墦鍗板綋鍓嶅懡涓綆浠风殑鐘舵€?
            self.logger.warning(
                "[浣庝环] %s->%s %s 楼%.0f (闃堝€悸?.0f, 涓婃鎺ㄩ€伮?s) -> %s",
                route.from_name, route.to_name, date,
                bp.price, route.alert_threshold,
                f"{last:.0f}" if last else "-",
                "鎺ㄩ€? if should_push else f"璺宠繃({reason})",
            )

            if should_push and self.notifier:
                ok = self._push(route, date, bp, last)
                if ok and self.storage:
                    self.storage.set_alert_state(route_key, bp.price)

    def _should_push(self, cur: float, last: Optional[float]):
        if last is None:
            return True, "棣栨"
        diff = cur - last
        if diff <= -self.push_drop_min:
            return True, f"闄嵚-diff:.0f}"
        if diff >= self.push_rise_min:
            return True, f"娑diff:.0f}"
        return False, f"娉㈠姩楼{diff:+.0f}(<闃堝€?"

    def _push(self, route: Route, date: str, p: FlightPrice,
              last: Optional[float]) -> bool:
        diff_txt = ""
        emoji = "鉁堬笍"
        if last is not None:
            diff = p.price - last
            if diff <= 0:
                emoji = "馃搲"
                diff_txt = f"锛堣緝涓婃闄?楼{-diff:.0f}锛?
            else:
                emoji = "馃搱"
                diff_txt = f"锛堣緝涓婃娑?楼{diff:.0f}锛?

        title = (f"{emoji} {route.from_name}鈫抺route.to_name} {date} "
                 f"楼{p.price:.0f}{diff_txt}")

        # markdown 璇︾粏
        view_url = self._build_view_url(route, date, p.platform)
        desp = (
            f"## 鏈虹エ浣庝环鎻愰啋\n\n"
            f"- **鑸嚎**锛歿route.from_name}锛坽route.from_code}锛?鈫?"
            f"{route.to_name}锛坽route.to_code}锛塡n"
            f"- **鏃ユ湡**锛歿date}\n"
            f"- **褰撳墠鏈€浣庝环**锛?*楼{p.price:.0f}**\n"
            f"- **璁惧畾闃堝€?*锛毬route.alert_threshold:.0f}\n"
            f"- **鏉ユ簮**锛歿p.platform}\n"
            f"- **鎶撳彇鏃堕棿**锛歿p.fetched_at}\n"
        )
        if last is not None:
            desp += f"- **涓婃鎺ㄩ€佷环**锛毬last:.0f}\n"
        desp += f"\n[馃憠 鍦?{p.platform} 鏌ョ湅璇︽儏]({view_url})\n"
        return self.notifier.send(title, desp)

    def _build_view_url(self, route: Route, date: str, platform: str) -> str:
        if platform == "ctrip":
            return (
                "https://m.ctrip.com/html5/flight/taro/first?from=inner"
                "&tripType=ONE_WAY"
                f"&dcity={route.from_code}&acity={route.to_code}&ddate={date}"
            )
        if platform == "tongcheng":
            return (
                "https://m.ly.com/ft/touch/book1"
                f"?date={date}&an=1&cn=0&baby=0"
                f"&fromcitycode={route.from_code}&fromCode={route.from_code}"
                f"&tocitycode={route.to_code}&toCode={route.to_code}"
                "&cabin=0&platcode=518&frompage=HOME"
            )
        if platform == "qunar":
            return (
                "https://touch.qunar.com/ncs/page/flightlist"
                f"?depCity={route.from_name}&arrCity={route.to_name}"
                f"&goDate={date}&from=touch_index_search"
                "&child=0&baby=0&cabinType=0"
            )
        if platform == "tuniu":
            return (
                "https://m.tuniu.com/flight/domestic/new/"
                f"{route.from_code}_{route.to_code}_OW_1_0_0"
                f"?deptDate={date}&isGo=0"
            )
        # fliggy 榛樿璧伴鐚?H5
        return (
            "https://outfliggys.m.taobao.com/app/trip/rx-flight-eco/pages/listing"
            f"?depCityCode={route.from_code}&arrCityCode={route.to_code}"
            f"&leaveDate={date}&adultPassengerNum=1&searchType=1"
        )

