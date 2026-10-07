"""Tiny Basilisk helpers shared by the setup modules."""


def attach_recorder(scSim, task_name, msg, period_ns):
    rec = msg.recorder(period_ns)
    scSim.AddModelToTask(task_name, rec)
    return rec
