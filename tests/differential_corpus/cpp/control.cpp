// control.cpp — control flow and the calls inside its bodies.

int classify(int value, const Report& report)
{
    if (value > 0)
    {
        report.warn();
    }
    else
    {
        report.info();
    }

    for (int i = 0; i < value; ++i)
    {
        report.tick(i);
    }

    while (report.pending())
    {
        report.drain();
    }

    switch (value)
    {
        case 1:
            report.one();
            break;
        default:
            report.other();
            break;
    }

    do
    {
        report.sweep();
    } while (report.again());

    try
    {
        report.attempt();
    }
    catch (const Error& error)
    {
        report.recover();
    }

    return report.total();
}
