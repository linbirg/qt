def move_stop():
    n = 4
    total = 0
    p = 0.3
    stop = 3
    for i in range(n):
        total += p*stop * i
        p = p / 2

    print('total:', total)


move_stop()
