import ridership_functions as rf
import matplotlib.pyplot as plt
import matplotlib as mp

def test_fig():
    fig = plt.figure()
    a = range(0,50,2)
    b = [0] * 25
    plt.plot(a, b, "-o")
    #plt.plot(a, orientation='horizontal', colors='b')
    plt.axis('off')
    fig.show()
