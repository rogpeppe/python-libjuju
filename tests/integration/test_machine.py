import asyncio
import pytest
import logging

from tempfile import NamedTemporaryFile

from .. import base


@base.bootstrapped
@pytest.mark.asyncio
async def test_status(event_loop):
    async with base.CleanModel() as model:
        await model.deploy(
            'ubuntu-0',
            application_name='ubuntu',
            series='trusty',
            channel='stable',
        )

        await asyncio.wait_for(
            model.block_until(lambda: len(model.machines)),
            timeout=240)
        machine = model.machines['0']

        assert machine.status in ('allocating', 'pending')
        assert machine.agent_status == 'pending'
        assert not machine.agent_version

        await asyncio.wait_for(
            model.block_until(lambda: (machine.status == 'running' and
                                       machine.agent_status == 'started' and
                                       machine.agent_version is not None)),
            timeout=480)

        assert machine.status == 'running'
        # there is some inconsistency in the message case between providers
        assert machine.status_message.lower() == 'running'
        assert machine.agent_status == 'started'
        assert machine.agent_version.major >= 2


@base.bootstrapped
@pytest.mark.asyncio
async def test_scp(event_loop):
    async with base.CleanModel() as model:
        logging.basicConfig(level=logging.DEBUG)
        print('model loop is {}'.format(id(model.loop)))
        await model.add_machine()
        await asyncio.wait_for(
            model.block_until(lambda: model.machines),
            timeout=240)
        machine = model.machines['0']
        await asyncio.wait_for(
            model.block_until(lambda: (machine.status == 'running' and
                                       machine.agent_status == 'started')),
            timeout=480)

        with NamedTemporaryFile() as f:
            f.write(b'testcontents')
            f.flush()
            print('scp_to {} -> {}'.format(f.name, 'testfile'))
            await machine.scp_to(f.name, 'testfile')
            print('scp_to complete')

        with NamedTemporaryFile() as f:
            print('scp_from {} -> {}'.format('testfile', f.name))
            await machine.scp_from('testfile', f.name)
            assert f.read() == b'testcontents'
            print('scp_from complete')
