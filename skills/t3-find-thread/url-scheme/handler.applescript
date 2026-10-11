-- "T3 Open": handles t3open://<thread-id> by delegating to t3-open-thread (exact-open via cmd+k).
-- t3-open-thread validates the id itself; the URL is passed shell-quoted.
on open location theURL
	set cmd to "export PATH=/opt/homebrew/bin:$HOME/.local/bin:$HOME/.local/share/mise/shims:/usr/bin:/bin; " & ¬
		"mkdir -p $HOME/.cache/t3-find-thread; " & ¬
		"$HOME/.local/bin/t3-open-thread " & quoted form of theURL & ¬
		" >>$HOME/.cache/t3-find-thread/open.log 2>&1 &"
	do shell script cmd
end open location

on run
	-- launched directly (no URL): nothing to do
end run
