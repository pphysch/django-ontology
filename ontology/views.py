from django.shortcuts import render
from django.http.request import HttpRequest
from . import models
import logging

logger = logging.getLogger(__name__)

# Create your views here.
def log_action(request: HttpRequest, action: "models.Action", target: "models.EntityModel"):
    logger.info("User:%s Action:%s Target:%s (%s)", request.user, action, target, request.META)