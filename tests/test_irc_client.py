"""Regression scenarios: python -m unittest discover -s tests -v."""
import socket
import threading
import unittest
from unittest.mock import Mock, patch

from albikirc.irc_client import IRCClient


class IRCClientTests(unittest.TestCase):
    def setUp(self):
        self.client = IRCClient(activity_summaries=False)
        self.client.nick = 'me'
        self.client._emit_status = Mock()
        self.client._emit_users = Mock()
        self.client._emit_message = Mock()
        self.peers = []
        self.release = threading.Event()
        self.workers = []

    def tearDown(self):
        self.release.set()
        self.client.disconnect()
        for peer in self.peers:
            peer.close()
        for worker in self.workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())

    def line(self, text):
        self.client._handle_line(text)

    def names(self, names, channel='#test'):
        self.line(f':server 353 me = {channel} :{names}')

    def end_names(self, channel='#test'):
        self.line(f':server 366 me {channel} :End of NAMES')

    def users(self, channel='#test'):
        return self.client._chan_users[self.client._casefold(channel)]

    def socket_pair(self):
        client_sock, peer = socket.socketpair()
        self.peers.append(peer)
        return client_sock

    def track_worker(self):
        worker = self.client._connect_thread
        self.workers.append(worker)
        return worker

    def test_names_chunks_accumulate_and_new_refresh_removes_stale_users(self):
        self.names('me @Alice')
        self.names('+Bob Carol')
        self.end_names()
        self.assertEqual(self.users(), {'me', 'Alice', 'Bob', 'Carol'})
        self.names('me Carol')
        self.end_names()
        self.assertEqual(self.users(), {'me', 'Carol'})
        self.assertFalse(self.client._names_pending)

    def test_interleaved_membership_changes_override_later_chunks(self):
        self.names('me Alice')
        self.line(':aLiCe!u@host PART #test :bye')
        self.line(':Dave!u@host JOIN #test')
        self.line(':Bob!u@host QUIT :bye')
        self.line(':Carol!u@host NICK :Cathy')
        self.names('Alice Bob Carol')
        self.end_names()
        self.assertEqual(self.users(), {'me', 'Dave', 'Cathy'})

    def test_nick_change_does_not_add_user_to_unrelated_pending_channel(self):
        self.names('me Alice')
        self.names('me Bob', '#other')
        self.line(':ALICE!u@host NICK :Alicia')
        self.names('Carol', '#other')
        self.end_names('#other')
        self.assertEqual(self.users('#other'), {'me', 'Bob', 'Carol'})
        self.assertEqual(self.users(), {'me', 'Alicia'})

    def test_events_before_first_chunk_survive_initial_names(self):
        self.line(':me!u@host JOIN #test')
        self.line(':Dave!u@host JOIN #test')
        self.line(':Alice!u@host PART #test')
        self.names('me Alice')
        self.end_names()
        self.assertEqual(self.users(), {'me', 'Dave'})

    def test_nick_change_then_quit_before_snapshot_chunk(self):
        self.names('me')
        self.line(':Alice!u@host NICK :Alicia')
        self.line(':Alicia!u@host QUIT :bye')
        self.names('Alice')
        self.end_names()
        self.assertEqual(self.users(), {'me'})

    def test_case_insensitive_quit_kick_and_nick(self):
        self.names('me Alice Bob Carol')
        self.end_names()
        self.line(':ALICE!u@host QUIT :bye')
        self.line(':op!u@host KICK #test bOB :bye')
        self.line(':cAROL!u@host NICK :Cara')
        self.assertEqual(self.users(), {'me', 'Cara'})

    def test_rfc1459_mapping_and_status_prefixes(self):
        self.names('~Owner &Admin @Op %Half +Voice [Nick]')
        self.end_names()
        self.line(':{nick}!u@host PART #TEST')
        self.assertEqual(self.users(), {'Owner', 'Admin', 'Op', 'Half', 'Voice'})

    def test_server_advertised_ascii_mapping_and_prefix(self):
        self.line(':server 005 me CASEMAPPING=ascii PREFIX=(ov)!+ :supported')
        self.names('!Alice [Nick] {Nick}')
        self.end_names()
        self.line(':{nick}!u@host QUIT :bye')
        self.assertEqual(self.users(), {'Alice', '[Nick]'})

    def test_own_part_or_kick_clears_channel_and_allows_fresh_rejoin(self):
        for departure in (':ME!u@host PART #test', ':op!u@host KICK #test ME :bye'):
            with self.subTest(departure=departure):
                self.names('me Alice')
                self.line(departure)
                self.assertNotIn('#test', self.client._chan_users)
                self.assertNotIn('#test', self.client._names_pending)
                self.assertIn((('#test', []), {}), self.client._emit_users.call_args_list)
                self.line(':me!u@host JOIN #test')
                self.names('me Bob')
                self.end_names()
                self.assertEqual(self.users(), {'me', 'Bob'})

    def test_disconnect_clears_displayed_users(self):
        self.names('me Alice')
        self.client.disconnect()
        self.client._emit_users.assert_called_with('#test', [])
        self.assertFalse(self.client._chan_users)
        self.assertFalse(self.client._names_pending)

    def test_slow_setup_returns_immediately_and_can_be_cancelled(self):
        entered = threading.Event()
        sock = self.socket_pair()

        def slow_connect(*args, **kwargs):
            entered.set()
            self.assertTrue(self.release.wait(2))
            return sock

        with patch('albikirc.irc_client.socket.create_connection', side_effect=slow_connect):
            self.client.connect('slow.example', 6667, 'me', use_tls=False)
            worker = self.track_worker()
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.client.connecting)
            self.assertFalse(self.client.connected)
            self.client.disconnect()
            self.release.set()
            worker.join(2)
        self.assertFalse(self.client.connected)
        self.assertFalse(self.client.connecting)
        self.assertEqual(sock.fileno(), -1)

    def test_late_old_attempt_cannot_replace_new_connection(self):
        entered = threading.Event()
        old_sock, new_sock = self.socket_pair(), self.socket_pair()

        def connect(address, *args, **kwargs):
            if address[0] == 'old.example':
                entered.set()
                self.assertTrue(self.release.wait(2))
                return old_sock
            return new_sock

        with patch('albikirc.irc_client.socket.create_connection', side_effect=connect):
            self.client.connect('old.example', 6667, 'old', use_tls=False)
            old_worker = self.track_worker()
            self.assertTrue(entered.wait(1))
            self.client.connect('new.example', 6667, 'new', use_tls=False)
            self.track_worker().join(2)
            self.assertTrue(self.client.connected)
            self.release.set()
            old_worker.join(2)
        self.assertIs(self.client._sock, new_sock)
        self.assertEqual(self.client.nick, 'new')
        self.assertEqual(old_sock.fileno(), -1)
        self.assertNotEqual(new_sock.fileno(), -1)

    def test_old_reader_exit_does_not_clear_new_connection(self):
        old_sock, new_sock = self.socket_pair(), self.socket_pair()
        with patch('albikirc.irc_client.socket.create_connection',
                   side_effect=[old_sock, new_sock]):
            self.client.connect('old.example', 6667, 'old', use_tls=False)
            self.track_worker().join(2)
            old_reader = self.client._rx_thread
            # Leave the old socket open until the replacement has been installed.
            with patch.object(self.client, '_close_socket'):
                self.client.connect('new.example', 6667, 'new', use_tls=False)
                self.track_worker().join(2)
                with self.client._state_lock:
                    self.names('new Alice')
                self.peers[0].shutdown(socket.SHUT_RDWR)
                old_reader.join(2)
            self.assertFalse(old_reader.is_alive())
            self.assertTrue(self.client.connected)
            self.assertIs(self.client._sock, new_sock)
            self.assertEqual(self.users(), {'new', 'Alice'})

    def test_slow_tls_can_be_cancelled_without_reviving_connection(self):
        entered = threading.Event()
        sock = self.socket_pair()
        context = Mock()

        def handshake(*args, **kwargs):
            entered.set()
            self.assertTrue(self.release.wait(2))
            return sock

        context.wrap_socket.side_effect = handshake
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock), \
                patch('albikirc.irc_client.ssl.create_default_context', return_value=context):
            self.client.connect('tls.example', 6697, 'me')
            worker = self.track_worker()
            self.assertTrue(entered.wait(1))
            self.client.disconnect()
            self.release.set()
            worker.join(2)
        self.assertFalse(self.client.connected)
        self.assertEqual(sock.fileno(), -1)

    def test_late_failure_does_not_overwrite_new_connection_status(self):
        entered = threading.Event()
        new_sock = self.socket_pair()

        def connect(address, *args, **kwargs):
            if address[0] == 'old.example':
                entered.set()
                self.assertTrue(self.release.wait(2))
                raise OSError('old failure')
            return new_sock

        with patch('albikirc.irc_client.socket.create_connection', side_effect=connect):
            self.client.connect('old.example', 6667, 'old', use_tls=False)
            old_worker = self.track_worker()
            self.assertTrue(entered.wait(1))
            self.client.connect('new.example', 6667, 'new', use_tls=False)
            self.track_worker().join(2)
            self.release.set()
            old_worker.join(2)
        self.assertTrue(self.client.connected)
        self.client._emit_status.assert_called_with('Connected to new.example:6667')

    def test_registration_keeps_password_first_and_uses_real_name(self):
        sock = self.socket_pair()
        self.client.server_password = 'test-password'
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock):
            self.client.connect('example', 6667, 'me', real_name='Test User', use_tls=False)
            self.track_worker().join(2)
        self.peers[0].settimeout(1)
        self.assertEqual(self.peers[0].recv(4096),
                         b'PASS test-password\r\nNICK me\r\nUSER me 0 * :Test User\r\n')

    def test_blocked_registration_does_not_block_disconnect(self):
        entered = threading.Event()
        sock = Mock()

        def sendall(data):
            entered.set()
            self.assertTrue(self.release.wait(2))

        sock.sendall.side_effect = sendall
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock):
            self.client.connect('example', 6667, 'me', use_tls=False)
            worker = self.track_worker()
            self.assertTrue(entered.wait(1))
            # This would deadlock if the network write held the state lock.
            self.client.disconnect()
            self.release.set()
            worker.join(2)
        self.assertFalse(self.client.connected)
        sock.close.assert_called_once()

    def test_reader_processes_membership_and_can_send_chat(self):
        sock = self.socket_pair()
        complete = threading.Event()

        def users_updated(target, users):
            if target == '#test' and set(users) == {'me', 'Alicia', 'Bob'}:
                complete.set()

        self.client._emit_users.side_effect = users_updated
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock):
            self.client.connect('example', 6667, 'me', use_tls=False)
            self.track_worker().join(2)
        peer = self.peers[0]
        peer.settimeout(1)
        peer.recv(4096)  # Drain registration.
        peer.sendall(b':me!u@host JOIN #test\r\n'
                     b':server 353 me = #test :me Alice\r\n'
                     b':Alice!u@host NICK :Alicia\r\n'
                     b':server 353 me = #test :Bob\r\n'
                     b':server 366 me #test :End of NAMES\r\n')
        self.assertTrue(complete.wait(1))
        self.client.send_message('#test', 'hello')
        self.assertEqual(peer.recv(4096), b'PRIVMSG #test :hello\r\n')

    def test_automatic_reconnect_worker_rejoins_after_welcome(self):
        old_sock, new_sock = self.socket_pair(), self.socket_pair()
        with patch('albikirc.irc_client.socket.create_connection',
                   side_effect=[old_sock, new_sock]), \
                patch('albikirc.irc_client.threading.Timer'):
            self.client.connect('example', 6667, 'me', use_tls=False)
            self.track_worker().join(2)
            self.client.join_channel('#test', 'channel-key')
            serial = self.client._connection_serial
            reader = self.client._rx_thread
            self.peers[0].shutdown(socket.SHUT_RDWR)
            reader.join(2)
            self.assertIsNotNone(self.client._reconnect_timer)
            self.client._reconnect(serial)
            self.track_worker().join(2)
            self.assertTrue(self.client.connected)
            peer = self.peers[1]
            peer.settimeout(1)
            peer.recv(4096)  # Drain registration.
            peer.sendall(b':server 001 me :Welcome back\r\n')
            self.assertEqual(peer.recv(4096), b'JOIN #test channel-key\r\n')

    def test_failed_background_retry_schedules_next_backoff(self):
        sock = self.socket_pair()
        with patch('albikirc.irc_client.socket.create_connection',
                   side_effect=[sock, OSError('retry failed')]), \
                patch('albikirc.irc_client.threading.Timer') as timer:
            self.client.connect('example', 6667, 'me', use_tls=False)
            self.track_worker().join(2)
            serial = self.client._connection_serial
            reader = self.client._rx_thread
            self.peers[0].shutdown(socket.SHUT_RDWR)
            reader.join(2)
            self.client._reconnect(serial)
            self.track_worker().join(2)
            self.assertFalse(self.client.connected)
            self.assertFalse(self.client.connecting)
            self.assertIsNotNone(self.client._reconnect_timer)
            self.assertEqual([call.args[0] for call in timer.call_args_list], [2, 4])

    def test_connection_failure_resets_state_and_reports_error(self):
        with patch('albikirc.irc_client.socket.create_connection', side_effect=OSError('refused')):
            self.client.connect('bad.example', 6667, 'me', use_tls=False)
            self.track_worker().join(2)
        self.assertFalse(self.client.connecting)
        self.assertFalse(self.client.connected)
        self.client._emit_status.assert_called_with('Connect failed: refused')

    def test_tls_failure_closes_socket(self):
        sock = self.socket_pair()
        context = Mock()
        context.wrap_socket.side_effect = OSError('TLS failed')
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock), \
                patch('albikirc.irc_client.ssl.create_default_context', return_value=context):
            self.client.connect('tls.example', 6697, 'me')
            self.track_worker().join(2)
        self.assertEqual(sock.fileno(), -1)
        self.assertFalse(self.client.connected)
        self.client._emit_status.assert_called_with('Connect failed: TLS failed')

    def test_reader_eof_clears_users_and_socket(self):
        sock = self.socket_pair()
        with patch('albikirc.irc_client.socket.create_connection', return_value=sock):
            self.client.connect('example', 6667, 'me', use_tls=False)
            self.track_worker().join(2)
        reader = self.client._rx_thread
        with self.client._state_lock:
            self.names('me Alice')
        self.peers[0].shutdown(socket.SHUT_RDWR)
        reader.join(2)
        self.assertFalse(reader.is_alive())
        self.assertFalse(self.client.connected)
        self.assertIsNone(self.client._sock)
        self.assertFalse(self.client._chan_users)
        self.client._emit_users.assert_called_with('#test', [])


if __name__ == '__main__':
    unittest.main()
