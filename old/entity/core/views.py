from django.shortcuts import render
from . import models

# Create your views here.

def view(request):
    return render(request, "_base.html")

def comment_thread(request, pk):
    comment = models.Comment.objects.get(pk=pk)
    return render(request, "comment_thread.html", {"comment": comment, "show_replies":3 })

def comment_delete(request, pk):
    print("deleting comment " + str(pk))
    comment = models.Comment.objects.get(pk=pk)
    comment.delete(hard_delete=False)
    return render(request, "comment.html", {"comment": comment, "show_replies": 0})