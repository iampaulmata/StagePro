from PySide6.QtCore import Qt, QSize, QRectF


def resize_viewer_to_viewport(view, viewer, fit_margin_px: int, is_portrait: bool) -> None:
    margin = fit_margin_px
    vp = view.viewport().size()
    w = max(200, vp.width() - 2 * margin)
    h = max(200, vp.height() - 2 * margin)

    # swap size in portrait so the *rotated* content fills
    if is_portrait:
        viewer.setFixedSize(QSize(h, w))
    else:
        viewer.setFixedSize(QSize(w, h))


def fit_view_to_content(view, proxy, resize_viewer_to_viewport_callback, fit_mode: str) -> None:
    resize_viewer_to_viewport_callback()
    rect: QRectF = proxy.sceneBoundingRect()
    if rect.isNull():
        return
    view.setSceneRect(rect)
    if fit_mode == "fill":
        view.fitInView(rect, Qt.KeepAspectRatioByExpanding)
    else:
        view.fitInView(rect, Qt.KeepAspectRatio)


def apply_orientation_transform(proxy, is_portrait: bool, portrait_rotation_deg: int, fit_view_to_content_callback) -> None:
    if is_portrait:
        proxy.setRotation(portrait_rotation_deg)
    else:
        proxy.setRotation(0)
    fit_view_to_content_callback()
