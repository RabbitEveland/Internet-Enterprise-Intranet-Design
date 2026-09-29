import tkinter as tk

def start_gui():
    root = tk.Tk()
    root.title("客户端界面")
    tk.Label(root, text="客户端运行中...").pack(pady=20)
    root.mainloop()

if __name__ == "__main__":
    start_gui()
