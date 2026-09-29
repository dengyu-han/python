import tkinter
import webbrowser


class VIPVideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title('VIP免费追剧神器')
        self.root.geometry('480x280')
        self.create_widgets()

    def create_widgets(self):
        # 提示标签
        label_movie_link = tkinter.Label(self.root, text='输入视频网址：')
        label_movie_link.place(x=20, y=30, width=100, height=30)

        # 输入框
        self.entry_movie_link = tkinter.Entry(self.root)
        self.entry_movie_link.place(x=125, y=30, width=260, height=30)

        # 清空按钮
        button_clear = tkinter.Button(self.root, text='清空', command=self.empty)
        button_clear.place(x=400, y=30, width=50, height=30)

        # 平台按钮
        button_iqiyi = tkinter.Button(self.root, text='爱奇艺', command=self.open_iqiyi)
        button_iqiyi.place(x=25, y=80, width=80, height=40)

        button_tencent = tkinter.Button(self.root, text='腾讯视频', command=self.open_tencent)
        button_tencent.place(x=125, y=80, width=80, height=40)

        button_youku = tkinter.Button(self.root, text='优酷视频', command=self.open_youku)
        button_youku.place(x=225, y=80, width=80, height=40)

        # 播放按钮
        button_play = tkinter.Button(self.root, text='播放VIP视频', command=self.play_video)
        button_play.place(x=325, y=80, width=125, height=40)

        # 提示标签
        text = '本案例仅供学习使用，不可作为他用。'
        label_remind = tkinter.Label(self.root, text=text, fg='red', font=('Arial', 15))
        label_remind.place(x=50, y=150, width=400, height=30)

        # 设置窗口大小
        self.root.resizable(False, False)

    def open_iqiyi(self):
        webbrowser.open('https://www.iqiyi.com')

    def open_tencent(self):
        webbrowser.open('https://v.qq.com')

    def open_youku(self):
        webbrowser.open('https://www.youku.com')

    def play_video(self):
        video = self.entry_movie_link.get()
        # 调用多个解析接口
        webbrowser.open('https://jx.xmflv.com/?url=' + video)
        webbrowser.open('https://jx.xmflv.cc/?url=' + video)
        webbrowser.open('https://jx.77flv.cc/?url=' + video)

    def empty(self):
        self.entry_movie_link.delete(0, 'end')


if __name__ == '__main__':
    root = tkinter.Tk()
    app = VIPVideoApp(root)
    root.mainloop()
