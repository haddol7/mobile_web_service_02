from django import forms
from .models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ("title", "text", "image")
        labels = {"title": "제목", "text": "내용", "image": "사진"}


class PhotoSearchForm(forms.Form):
    from .content_rules import THEMES
    q = forms.CharField(required=False, max_length=80, label="사진 속 글자 검색",
                        widget=forms.TextInput(attrs={"placeholder":"간판·메뉴·책 제목 검색"}))
    theme = forms.ChoiceField(required=False, choices=[("", "전체 테마"), *THEMES.items(), ("unclassified", "미분류")], label="테마")
    tag = forms.CharField(required=False, max_length=30, label="태그")

