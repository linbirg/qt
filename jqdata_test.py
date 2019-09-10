import jqdatasdk as jq

jq.auth('18602166903', '13773275')

df = jq.get_all_securities()[:3]

print(df)

bd = jq.get_baidu_factor(
    category='csi800', day='2018-06-25', stock='600519.XSHG', province=None)

print(bd)
