import brownie
from brownie import Wei, accounts, Contract, config

# test cloning our strategy, make sure the cloned strategy still works just fine by sending funds to it
def test_cloning(
    gov,
    token,
    vault,
    strategist,
    whale,
    strategy,
    keeper,
    rewards,
    chain,
    StrategyConvexCrvCvxPairsClonable,
    rewardsContract,
    pid,
    amount,
    pool,
    strategy_name,
    sleep_time,
    use_crv,
):
    # Shouldn't be able to call initialize again
    with brownie.reverts():
        strategy.initialize(
            vault,
            strategist,
            rewards,
            keeper,
            use_crv,
            {"from": gov},
        )

    ## clone our strategy
    tx = strategy.cloneConvexCrvCvxPairs(
        vault, strategist, rewards, keeper, use_crv, {"from": gov}
    )
    newStrategy = StrategyConvexCrvCvxPairsClonable.at(tx.return_value)

    # Shouldn't be able to call initialize again
    with brownie.reverts():
        newStrategy.initialize(
            vault,
            strategist,
            rewards,
            keeper,
            use_crv,
            {"from": gov},
        )

    ## shouldn't be able to clone a clone
    with brownie.reverts():
        newStrategy.cloneConvexCrvCvxPairs(
            vault, strategist, rewards, keeper, use_crv, {"from": gov}
        )

    # revoke to send all funds back to vault
    vault.revokeStrategy(strategy, {"from": gov})

    # attach our new strategy
    vault.addStrategy(newStrategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    assert vault.withdrawalQueue(1) == newStrategy
    assert vault.strategies(newStrategy)[2] == 10_000
    assert vault.withdrawalQueue(0) == strategy
    assert vault.strategies(strategy)["debtRatio"] == 0

    ## deposit to the vault after approving; this is basically just our simple_harvest test
    before_pps = vault.pricePerShare()
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2 ** 256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    # harvest, store asset amount
    newStrategy.harvest({"from": gov})
    old_assets_dai = vault.totalAssets()
    assert old_assets_dai > 0
    assert token.balanceOf(newStrategy) == 0
    assert newStrategy.estimatedTotalAssets() > 0
    assert rewardsContract.balanceOf(newStrategy) > 0
    print("\nStarting Assets: ", old_assets_dai / 1e18)
    print("\nAssets Staked: ", rewardsContract.balanceOf(newStrategy) / 1e18)

    # simulate some earnings
    chain.sleep(sleep_time)
    chain.mine(1)

    # harvest after a day, store new asset amount
    newStrategy.harvest({"from": gov})
    new_assets_dai = vault.totalAssets()
    # we can't use strategyEstimated Assets because the profits are sent to the vault
    assert new_assets_dai >= old_assets_dai
    print("\nAssets after 2 days: ", new_assets_dai / 1e18)

    # Display estimated APR based on the two days before the pay out
    print(
        "\nEstimated APR: ",
        "{:.2%}".format(
            ((new_assets_dai - old_assets_dai) * (365 * (86400 / sleep_time)))
            / (newStrategy.estimatedTotalAssets())
        ),
    )

    # simulate a day of waiting for share price to bump back up
    chain.sleep(86400)
    chain.mine(1)

    # withdraw and confirm we made money
    vault.withdraw({"from": whale})
    assert token.balanceOf(whale) >= startingWhale
    assert vault.pricePerShare() > before_pps
