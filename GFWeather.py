"""
每天定时给多个女友发给微信暖心话
核心代码。
"""
import os
import time
from datetime import datetime
import itchat
import requests
import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from bs4 import BeautifulSoup
from simplejson import JSONDecodeError

import city_dict

# fire the job again if it was missed within GRACE_PERIOD
GRACE_PERIOD = 15 * 60


class GFWeather:
    """
    每日天气与提醒。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/67.0.3396.87 Safari/537.36',
    }
    dictum_channel_name = {1: 'ONE●一个', 2: '词霸(每日英语)', 3: '土味情话'}

    def __init__(self):
        self.girlfriend_list, self.alarm_hour, self.alarm_minute, self.dictum_channel = self.get_init_data()

    def get_init_data(self):
        """
        初始化基础数据。
        :return: (dict,int,int,int)
            1.dict 需要发送的用户的信息；
            2.int 时；
            3.int 分；
            4.int 格言渠道。（1: 'ONE●一个', 2: '词霸(每日英语)', 3: '土味情话'）
        """
        with open('_config.yaml', 'r', encoding='utf-8') as file:
            config = yaml.load(file, Loader=yaml.Loader)

        alarm_timed = config.get('alarm_timed').strip()
        init_msg = '每天定时发送时间：{}\n'.format(alarm_timed)

        dictum_channel = config.get('dictum_channel', -1)
        init_msg += '格言获取渠道：{}\n'.format(self.dictum_channel_name.get(dictum_channel, '无'))

        girlfriend_list = []
        girlfriend_infos = config.get('girlfriend_infos')
        for girlfriend in girlfriend_infos:
            girlfriend.get('wechat_name').strip()
            # 根据城市名称获取城市编号，用于查询天气。查看支持的城市为：http://cdn.sojson.com/_city.json
            city_name = girlfriend.get('city_name').strip()
            city_code = city_dict.city_dict.get(city_name)
            # 输入城市名称对应的城市代码不在 city_dict.py 文件中则停止
            if not city_code:
                print('您输入的城市无法收取到天气信息。')
                break
            girlfriend['city_code'] = city_code
            girlfriend_list.append(girlfriend)
            print_msg = (
                '女朋友的微信昵称：{wechat_name}\n\t女友所在城市名称：{city_name}\n\t'
                '在一起的第一天日期：{start_date}\n\t最后一句为：{sweet_words}\n'.format(**girlfriend))
            init_msg += print_msg

        print('*' * 50)
        print(init_msg)

        hour, minute = [int(x) for x in alarm_timed.split(':')]
        return girlfriend_list, hour, minute, dictum_channel

    # 静态方法
    @staticmethod
    def is_online(auto_login=False):
        """
        判断是否还在线。
        :param auto_login: bool,如果掉线了则自动登录(默认为 False)。
        :return: bool,当返回为 True 时，在线；False 已断开连接。
        """

        def _online():
            """
            通过获取好友信息，判断用户是否还在线。
            :return: bool,当返回为 True 时，在线；False 已断开连接。
            """
            try:
                if itchat.search_friends():
                    return True
            except IndexError:
                return False
            return True

        if _online():
            return True
        # 仅仅判断是否在线。
        if not auto_login:
            return _online()

        # 登陆，尝试 5 次。
        for _ in range(5):
            # 命令行显示登录二维码。
            if os.environ.get('MODE') == 'server':
                itchat.auto_login(enableCmdQR=2, hotReload=True)
            else:
                # 保留登录的状态，至少在后面的几次登录过程中不会再次扫描二维码，该参数生成一个静态文件itchat.pkl用于存储登录状态
                itchat.auto_login(hotReload=True)
            if _online():
                print('登录成功')
                return True

        print('登录成功')
        return False

    def run(self):
        """
        主运行入口。
        :return:None
        """
        # 自动登录
        if not self.is_online(auto_login=True):
            print("不在线")
            return
        for girlfriend in self.girlfriend_list:
            wechat_name = girlfriend.get('wechat_name')
            friends = itchat.search_friends(name=wechat_name)
            if not friends:
                print('昵称『{}』有误。'.format(wechat_name))
                return
            name_uuid = friends[0].get('UserName')
            girlfriend['name_uuid'] = name_uuid

        # 定时任务
        scheduler = BlockingScheduler()
        # 每天9：30左右给女朋友发送每日一句
        scheduler.add_job(self.start_today_info, 'cron', hour=self.alarm_hour,
                          minute=self.alarm_minute, misfire_grace_time=GRACE_PERIOD)
        # 每隔 2 分钟发送一条数据用于测试。
        # scheduler.add_job(self.start_today_info, 'interval', seconds=120)
        scheduler.start()

    def start_today_info(self, is_test=False):
        """
        每日定时开始处理。
        :param is_test:bool, 测试标志，当为True时，不发送微信信息，仅仅获取数据。
        :return: None.
        """
        print('*' * 50)
        print('获取相关信息...')

        if self.dictum_channel == 1:
            dictum_msg = self.get_dictum_info()
        elif self.dictum_channel == 2:
            dictum_msg = self.get_ciba_info()
        elif self.dictum_channel == 3:
            dictum_msg = self.get_lovelive_info()
        else:
            dictum_msg = ''

        for girlfriend in self.girlfriend_list:
            city_code = girlfriend.get('city_code')
            start_date = girlfriend.get('start_date').strip()
            sweet_words = girlfriend.get('sweet_words')
            today_msg = self.get_weather_info(
                dictum_msg, city_code=city_code, start_date=start_date, sweet_words=sweet_words)
            name_uuid = girlfriend.get('name_uuid')
            wechat_name = girlfriend.get('wechat_name')
            print('给『{}』发送的内容是:\n{}'.format(wechat_name, today_msg))

            if not is_test:
                if self.is_online(auto_login=True):
                    # toUserName 发送对象，如果留空, 将发送给自己，返回值为True或者False
                    itchat.send(today_msg, toUserName=name_uuid)
                # 防止信息发送过快。
                time.sleep(5)

        print('发送成功...\n')

    @staticmethod
    def is_json(resp):
        """
        判断数据是否能被 Json 化。 True 能，False 否。
        :param resp: request.
        :return: bool, True 数据可 Json 化；False 不能 JOSN 化。
        """
        try:
            resp.json()
            return True
        except JSONDecodeError:
            return False

    def get_ciba_info(self):
        """
        从词霸中获取每日一句，带英文。
        :return:str ,返回每日一句（双语）
        """
        print('获取格言信息（双语）...')
        resp = requests.get('http://open.iciba.com/dsapi')
        if resp.status_code == 200 and self.is_json(resp):
            content_dict = resp.json()
            content = content_dict.get('content')
            note = content_dict.get('note')
            return '{}\n{}\n'.format(content, note)

        print('没有获取到数据。')
        return None

    def get_dictum_info(self):
        """
        获取格言信息（从『一个。one』获取信息 http://wufazhuce.com/）
        :return: str， 一句格言或者短语。
        """
        print('获取格言信息...')
        user_url = 'http://wufazhuce.com/'
        resp = requests.get(user_url, headers=self.headers)
        if resp.status_code == 200:
            soup_texts = BeautifulSoup(resp.text, 'lxml')
            # 『one -个』 中的每日一句
            every_msg = soup_texts.find_all('div', class_='fp-one-cita')[0].find('a').text
            return every_msg + '\n'
        print('每日一句获取失败。')
        return None

    @staticmethod
    def get_lovelive_info():
        """
        从土味情话中获取每日一句。
        :return: str,土味情话。
        """
        print('获取土味情话...')
        resp = requests.get('https://api.lovelive.tools/api/SweetNothings')
        if resp.status_code == 200:
            return resp.text + '\n'

        print('土味情话获取失败。')
        return None

    def get_weather_info(self, dictum_msg, city_code, start_date, sweet_words):
        """
        获取天气信息。网址：https://www.sojson.com/blog/305.html .
        :param dictum_msg: str,发送给朋友的信息。
        :param city_code: str,城市对应编码。如：101030100
        :param start_date: str,恋爱第一天日期。如：2018-01-01
        :param sweet_words: str,来自谁的留言。如：来自你的朋友
        :return: str,需要发送的话。
        """
        print('获取天气信息...')
        weather_url = 'http://t.weather.sojson.com/api/weather/city/{}'.format(city_code)
        resp = requests.get(url=weather_url)
        if resp.status_code == 200 and self.is_json(resp) and resp.json().get('status') == 200:
            weather_dict = resp.json()
            # 今日天气
            today_weather = weather_dict.get('data').get('forecast')[1]
            # 今日日期
            today_time = (datetime.now().strftime('%Y{y}%m{m}%d{d} %H:%M:%S')
                          .format(y='年', m='月', d='日'))
            # 今日天气注意事项
            notice = today_weather.get('notice')
            # 温度
            high = today_weather.get('high')
            high_c = high[high.find(' ') + 1:]
            low = today_weather.get('low')
            low_c = low[low.find(' ') + 1:]
            temperature = '温度 : {}/{}'.format(low_c, high_c)

            # 风
            wind_direction = today_weather.get('fx')
            wind_level = today_weather.get('fl')
            wind = '{} : {}'.format(wind_direction, wind_level)

            # 空气指数
            aqi = today_weather.get('aqi')
            aqi = '空气 : {}'.format(aqi)

            # 在一起，一共多少天了，如果没有设置初始日期，则不用处理
            if start_date:
                try:
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                    day_delta = (datetime.now() - start_datetime).days
                    delta_msg = '宝贝这是我们在一起的第 {} 天。\n'.format(day_delta)
                except ValueError:
                    delta_msg = ''
            else:
                delta_msg = ''

            today_msg = (
                '{today_time}\n{delta_msg}{notice}。\n{temperature}\n'
                '{wind}\n{aqi}\n{dictum_msg}{sweet_words}\n'.format(
                    today_time=today_time, delta_msg=delta_msg, notice=notice,
                    temperature=temperature, wind=wind, aqi=aqi,
                    dictum_msg=dictum_msg, sweet_words=sweet_words if sweet_words else ""))
            return today_msg


if __name__ == '__main__':
    # 直接运行
    GFWeather().run()

    # 只查看获取数据，
    # GFWeather().start_today_info(True)

    # 测试获取词霸信息
    # ciba = GFWeather().get_ciba_info()
    # print(ciba)

    # 测试获取每日一句信息
    # dictum = GFWeather().get_dictum_info()
    # print(dictum)

    # 测试获取天气信息
    # wi = GFWeather().get_weather_info('好好学习，天天向上 \n', city_code='101030100',
    #                                   start_date='2018-01-01', sweet_words='美味的肉松')
    # print(wi)

    pass
