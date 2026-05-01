from django.db import models


class ContextStore(models.Model):
    scope = models.CharField(max_length=50)       # merchant / category / customer / trigger
    context_id = models.CharField(max_length=300, unique=True)
    version = models.IntegerField(default=1)
    payload = models.JSONField()
    stored_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["scope"]),
            models.Index(fields=["context_id"]),
        ]

    def __str__(self):
        return f"{self.scope}:{self.context_id}"