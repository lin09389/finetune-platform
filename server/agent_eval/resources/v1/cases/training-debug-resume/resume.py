def resume(checkpoints, trainer):
    checkpoint = checkpoints[-1]
    trainer.resume(checkpoint)
