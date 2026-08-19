import unittest
from unittest.mock import Mock, patch

from albikirc.irc_client import IRCClient


class ReconnectTests(unittest.TestCase):
    def connected_client(self) -> tuple[IRCClient, Mock]:
        client = IRCClient()
        sock = Mock()
        client.connected = True
        client._sock = sock
        client.nick = "tester"
        return client, sock

    def test_initial_welcome_does_not_repeat_join(self):
        client, sock = self.connected_client()
        client.join_channel("#python", "secret")
        client._handle_001(None, ["tester"], "Welcome")
        self.assertEqual(sock.sendall.call_count, 1)
        self.assertEqual(sock.sendall.call_args.args[0], b"JOIN #python secret\r\n")

    def test_reconnect_welcome_rejoins_remembered_channels(self):
        client, sock = self.connected_client()
        client._desired_channels = {
            "#python": ("#Python", None),
            "&local": ("&local", "secret"),
        }
        client._rejoining_after_reconnect = True
        client._handle_001(None, ["tester"], "Welcome back")
        self.assertEqual(
            [call.args[0] for call in sock.sendall.call_args_list],
            [b"JOIN #Python\r\n", b"JOIN &local secret\r\n"],
        )
        self.assertFalse(client._rejoining_after_reconnect)

    def test_auto_rejoin_can_be_disabled_without_forgetting_channels(self):
        client, sock = self.connected_client()
        client.auto_rejoin = False
        client._desired_channels = {"#python": ("#python", None)}
        client._rejoining_after_reconnect = True
        client._handle_001(None, ["tester"], "Welcome back")
        sock.sendall.assert_not_called()
        self.assertIn("#python", client._desired_channels)

    def test_part_and_kick_remove_channels_from_rejoin_set(self):
        client, sock = self.connected_client()
        client._desired_channels = {
            "#one": ("#one", None),
            "#two": ("#two", None),
        }
        client.part_channel("#one", "leaving")
        client._handle_kick("op!user@host", ["#two", "tester"], "bye")
        self.assertEqual(client._desired_channels, {})
        self.assertEqual(sock.sendall.call_args.args[0], b"PART #one :leaving\r\n")

    def test_server_confirmed_join_and_nick_change_are_retained(self):
        client, _sock = self.connected_client()
        client._connection_args = ("irc.example", 6697, "tester", None, True)
        client._handle_join("tester!user@host", ["#python"], None)
        client._handle_nick("tester!user@host", [], "newnick")
        self.assertEqual(client._desired_channels, {"#python": ("#python", None)})
        self.assertEqual(client._connection_args[2], "newnick")

    def test_unexpected_reader_eof_schedules_reconnect(self):
        client = IRCClient()
        sock = Mock()
        sock.recv.return_value = b""
        client._sock = sock
        client.connected = True
        client._intentional_disconnect = False
        client._connection_serial = 3
        stop_event = Mock()
        stop_event.is_set.return_value = False

        with patch.object(client, "_schedule_reconnect") as schedule:
            client._reader_loop(sock, stop_event, 3)

        schedule.assert_called_once_with(3)
        self.assertFalse(client.connected)
        self.assertIsNone(client._sock)

    def test_reconnect_uses_bounded_exponential_backoff(self):
        client = IRCClient(reconnect_initial_delay=2, reconnect_max_delay=5)
        client._intentional_disconnect = False
        client._connection_serial = 7
        client._connection_args = ("irc.example", 6697, "tester", None, True)
        timers = []

        def make_timer(delay, callback, args):
            timer = Mock()
            timer.delay = delay
            timer.callback = callback
            timer.args = args
            timers.append(timer)
            return timer

        with patch("albikirc.irc_client.threading.Timer", side_effect=make_timer):
            client._schedule_reconnect(7)
            client._reconnect_timer = None
            client._schedule_reconnect(7)
            client._reconnect_timer = None
            client._schedule_reconnect(7)

        self.assertEqual([timer.delay for timer in timers], [2, 4, 5])
        self.assertTrue(all(timer.daemon for timer in timers))
        self.assertTrue(all(timer.start.called for timer in timers))

    def test_intentional_disconnect_cancels_pending_reconnect(self):
        client = IRCClient()
        timer = Mock()
        client._reconnect_timer = timer
        client._intentional_disconnect = False
        client.disconnect()
        timer.cancel.assert_called_once_with()
        self.assertTrue(client._intentional_disconnect)
        self.assertIsNone(client._reconnect_timer)

    def test_disabled_reconnect_does_not_schedule(self):
        client = IRCClient(auto_reconnect=False)
        client._intentional_disconnect = False
        client._connection_serial = 2
        client._connection_args = ("irc.example", 6697, "tester", None, True)
        with patch("albikirc.irc_client.threading.Timer") as timer:
            client._schedule_reconnect(2)
        timer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
