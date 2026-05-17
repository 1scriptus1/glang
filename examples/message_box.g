let library = loadlib("user32")

// MessageBoxA(hwnd, text, caption, type)
// hwnd=0 means no parent window
library.MessageBoxA(0, "Hello from G!", "My Title", 0)