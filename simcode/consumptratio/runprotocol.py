from DRMETP import mainDRMETP
from TeleDTP import mainTELEDTP
import random
rate1list = [0]*8
rate2list = [0]*8
optratelist = [0]*8

round = 100
for i in range(round):
    mc_list = []
    rate_list = []
    linknum = 9
    for j in range(linknum):
        mc_list.append(random.randint(20,50))
    nodenum = 10
    for j in range(nodenum):
        rate_list.append(random.randint(20,50))

    for nodenum in range(3,11):
        rate1list[nodenum-3] += mainDRMETP(mc_list,rate_list,nodenum)
        rate2list[nodenum-3] += mainTELEDTP(mc_list,rate_list,nodenum)
        optratelist[nodenum-3] += (nodenum-1)/pow(0.8,nodenum-2)
    print("第"+str(i)+"次运行!")

import xlwt
book = xlwt.Workbook(encoding='utf-8')
sheet = book.add_sheet('sheet1')
for i in range(8):
    sheet.write(i, 0, rate1list[i]/round)
    sheet.write(i, 1, rate2list[i]/round)
    sheet.write(i, 2, optratelist[i]/round)
book.save("consumptrate.xls")