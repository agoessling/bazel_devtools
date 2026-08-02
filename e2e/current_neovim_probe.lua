local workspace = assert(vim.env.BAZEL_DEVTOOLS_WORKSPACE)
local contracts = {
  { file = "python/greeting.py", clients = { "basedpyright", "ruff" } },
  { file = "cpp/greeting.cc", clients = { "clangd" } },
  { file = "rust/greeting.rs", clients = { "rust_analyzer" } },
}

for _, contract in ipairs(contracts) do
  vim.cmd.edit(vim.fn.fnameescape(workspace .. "/" .. contract.file))
  local buffer = vim.api.nvim_get_current_buf()
  local attached = vim.wait(20000, function()
    local names = {}
    for _, client in ipairs(vim.lsp.get_clients({ bufnr = buffer })) do
      names[client.name] = true
    end
    for _, expected in ipairs(contract.clients) do
      if not names[expected] then
        return false
      end
    end
    return true
  end, 100)
  if not attached then
    local observed = {}
    for _, client in ipairs(vim.lsp.get_clients({ bufnr = buffer })) do
      table.insert(observed, client.name)
    end
    error(
      "expected "
        .. table.concat(contract.clients, ", ")
        .. " for "
        .. contract.file
        .. "; observed: "
        .. table.concat(observed, ", ")
    )
  end
end

vim.cmd.quitall({ bang = true })
