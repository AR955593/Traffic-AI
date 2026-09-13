package com.arrajput.trafficai.ui.main

import org.junit.Assert.assertNotNull
import org.junit.Test

class MainScreenViewModelTest {
    @Test
    fun testViewModelInitialization() {
        val viewModel = MainScreenViewModel()
        assertNotNull(viewModel)
    }
}
