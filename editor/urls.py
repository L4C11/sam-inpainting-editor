from django.urls import path
from editor.views import UploadImageView, SegmentLassoView, InpaintView, UpdateMaskView, RefineMaskView

urlpatterns = [
    path('upload/', UploadImageView.as_view(), name='api-upload'),
    path('segment-lasso/', SegmentLassoView.as_view(), name='api-segment-lasso'),
    path('update-mask/', UpdateMaskView.as_view(), name='api-update-mask'),
    path('refine-mask/', RefineMaskView.as_view(), name='api-refine-mask'),
    path('inpaint/', InpaintView.as_view(), name='api-inpaint'),
]