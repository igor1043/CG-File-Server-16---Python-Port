/* Shared by the in-game notice and its offscreen visual preview. */
static void retirement_feedback_paint(HDC dc, const RECT *client, const char *text)
{
    RECT heading = { 62, 15, client->right - 27, 39 };
    RECT body = { 27, 59, client->right - 27, client->bottom - 13 };
    RECT badge_text = { 27, 14, 51, 39 };
    HBRUSH background = CreateSolidBrush(RGB(255, 255, 255));
    HBRUSH badge = CreateSolidBrush(RGB(231, 239, 252));
    HBRUSH accent = CreateSolidBrush(RGB(9, 104, 248));
    HPEN border = CreatePen(PS_SOLID, 1, RGB(219, 227, 237));
    HGDIOBJ old_pen = SelectObject(dc, border);
    HGDIOBJ old_brush = SelectObject(dc, background);
    HFONT font;
    HGDIOBJ old_font;
    RECT stripe = { 0, 18, 5, client->bottom - 18 };

    FillRect(dc, client, background);
    RoundRect(dc, client->left, client->top, client->right - 1,
        client->bottom - 1, 20, 20);
    FillRect(dc, &stripe, accent);
    SelectObject(dc, GetStockObject(NULL_PEN));
    SelectObject(dc, badge);
    Ellipse(dc, 25, 14, 53, 42);
    SelectObject(dc, old_brush);
    SelectObject(dc, old_pen);
    DeleteObject(background);
    DeleteObject(badge);
    DeleteObject(accent);
    DeleteObject(border);

    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(9, 104, 248));
    font = CreateFontA(18, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, "Segoe UI");
    old_font = SelectObject(dc, font);
    DrawTextA(dc, "i", -1, &badge_text,
        DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
    SelectObject(dc, old_font);
    DeleteObject(font);

    font = CreateFontA(13, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, "Segoe UI");
    old_font = SelectObject(dc, font);
    DrawTextA(dc, "FIFA FRIENDS  |  CARREIRA", -1, &heading,
        DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
    SelectObject(dc, old_font);
    DeleteObject(font);

    border = CreatePen(PS_SOLID, 1, RGB(231, 237, 245));
    old_pen = SelectObject(dc, border);
    MoveToEx(dc, 27, 49, NULL);
    LineTo(dc, client->right - 27, 49);
    SelectObject(dc, old_pen);
    DeleteObject(border);

    SetTextColor(dc, RGB(52, 70, 81));
    font = CreateFontA(20, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_SWISS, "Segoe UI");
    old_font = SelectObject(dc, font);
    DrawTextA(dc, text, -1, &body, DT_LEFT | DT_WORDBREAK | DT_NOPREFIX);
    SelectObject(dc, old_font);
    DeleteObject(font);
}
